"""Importing this package registers every table on Base.metadata (used by Alembic)."""

from backend.app.models.user import User

__all__ = ["User"]
