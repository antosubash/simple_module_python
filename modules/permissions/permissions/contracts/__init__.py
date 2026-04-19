"""Permissions contracts — public interface for other modules."""

from permissions.contracts.schemas import (
    PermissionGroupOut,
    RoleOut,
    RolePermissionsOut,
    RolePermissionsUpdate,
)
from permissions.contracts.service import IPermissionService

__all__ = [
    "IPermissionService",
    "PermissionGroupOut",
    "RoleOut",
    "RolePermissionsOut",
    "RolePermissionsUpdate",
]
