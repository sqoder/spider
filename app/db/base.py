"""
SQLAlchemy declarative base with naming conventions.
All models inherit from this Base.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Naming conventions for constraints (critical for Alembic auto-migrations)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    metadata = metadata

    def to_dict(self):
        """Convert the model instance to a dictionary."""
        return {field.name: getattr(self, field.name) for field in self.__table__.columns}
