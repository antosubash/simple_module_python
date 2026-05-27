"""Backwards-compatibility re-export.

The canonical AuthMiddleware now lives in ``auth.middleware``. This shim
exists only to avoid breaking imports in downstream apps that referenced
``users.middleware.AuthMiddleware`` directly.
"""

from auth.middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]
