"""{{MODULE_NAME}} contracts — public interface for other modules."""

from {{PACKAGE_NAME}}.contracts.schemas import (
    {{SINGULAR_CLASS}}Create,
    {{SINGULAR_CLASS}}Out,
    {{SINGULAR_CLASS}}Update,
)

__all__ = [
    "{{SINGULAR_CLASS}}Create",
    "{{SINGULAR_CLASS}}Out",
    "{{SINGULAR_CLASS}}Update",
]
