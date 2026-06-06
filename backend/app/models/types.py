"""Cross-dialect column types.

Allows the same models to run on Postgres (production) and SQLite (tests).
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID when available, falls back to CHAR(36) for SQLite.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: D401
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PgUUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # noqa: D401
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        return value if dialect.name == "postgresql" else str(uuid.UUID(value))

    def process_result_value(self, value, dialect):  # noqa: D401
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)
