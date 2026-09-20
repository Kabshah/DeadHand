"""alembic/versions/0001_initial_schema.py — Initial schema: users, switches, otp_attempts.

SQLite-compatible: uses Integer instead of BigInteger (SQLite maps both to INTEGER anyway).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    op.create_table(
        "switches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("interval_hours", sa.Float(), nullable=False),
        sa.Column("next_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("interval_hours >= 0.01 AND interval_hours <= 8760", name="ck_switches_interval_hours"),
        sa.CheckConstraint(
            "status IN ('active', 'triggering', 'triggered', 'cancelled', 'failed_reveal')",
            name="ck_switches_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_switches_user_id", "switches", ["user_id"])
    op.create_index("ix_switches_next_deadline", "switches", ["next_deadline"])
    op.create_index("ix_switches_status", "switches", ["status"])

    op.create_table(
        "otp_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_attempts_user_id", "otp_attempts", ["user_id"])


def downgrade() -> None:
    op.drop_table("otp_attempts")
    op.drop_table("switches")
    op.drop_table("users")
