"""subscription upstream fields + device metadata

Revision ID: 0002_multi_device_meta
Revises: 0001_initial
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_multi_device_meta"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("upstream_max_connections", sa.Integer(), nullable=True, server_default="1"))
    op.add_column("subscriptions", sa.Column("upstream_status", sa.String(50), nullable=True))
    op.add_column("subscriptions", sa.Column("upstream_expire_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("notes", sa.Text(), nullable=True))

    op.add_column("devices", sa.Column("serial_number", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("app_name", sa.String(100), nullable=True))
    op.add_column("devices", sa.Column("app_version", sa.String(50), nullable=True))
    op.add_column("devices", sa.Column("last_seen_identifier", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "last_seen_identifier")
    op.drop_column("devices", "app_version")
    op.drop_column("devices", "app_name")
    op.drop_column("devices", "serial_number")
    op.drop_column("subscriptions", "notes")
    op.drop_column("subscriptions", "upstream_expire_at")
    op.drop_column("subscriptions", "upstream_status")
    op.drop_column("subscriptions", "upstream_max_connections")
