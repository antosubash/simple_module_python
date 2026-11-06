"""Backwards-compatibility re-export.

The canonical AuthMiddleware now lives in ``auth.web.middleware``. This shim
exists only to avoid breaking imports in downstream apps that referenced
``users.middleware.AuthMiddleware`` directly.
"""

from auth.web.middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]
