"""Sharing contracts — public interface for other modules."""

from sharing.contracts.cleanup import forget_resource
from sharing.contracts.schemas import ShareCandidate, ShareGrant, ShareOut
from sharing.contracts.subjects import (
    SubjectContext,
    SubjectProvider,
    SubjectRegistry,
    get_subject_registry,
)

__all__ = [
    "ShareCandidate",
    "ShareGrant",
    "ShareOut",
    "SubjectContext",
    "SubjectProvider",
    "SubjectRegistry",
    "forget_resource",
    "get_subject_registry",
]
