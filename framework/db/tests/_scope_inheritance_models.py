"""SQLAlchemy inheritance mappings for predicate-based scope registration."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, mapped_column


class InheritanceBase(DeclarativeBase):
    pass


class ScopeAnimal(InheritanceBase):
    __tablename__ = "scope_inheritance_animal"
    id = mapped_column(Integer, primary_key=True)
    kind = mapped_column(String)
    owner = mapped_column(String)
    __mapper_args__ = {"polymorphic_on": kind, "polymorphic_identity": "animal"}  # noqa: RUF012


class ScopeDog(ScopeAnimal):
    __mapper_args__ = {"polymorphic_identity": "dog"}  # noqa: RUF012
