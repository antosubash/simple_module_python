"""Every literal the site_lock module depends on."""

from __future__ import annotations

MODULE_NAME = "SiteLock"
MODULE_PACKAGE = "site_lock"

# Dependencies — names must match the other modules' ``ModuleMeta.name``.
MODULE_SETTINGS = "Settings"
MODULE_AUTH = "Auth"

# The gate endpoint. Double-underscore prefix keeps it clear of app routes.
UNLOCK_PATH = "/__unlock"
SESSION_KEY = "site_lock"

# Never gated: Kubernetes liveness/readiness probes must always succeed.
HEALTH_PREFIX = "/health"
API_PREFIX = "/api/"

# Duplicated rather than imported from ``users`` — site_lock must also work
# under the ``keycloak`` provider, which has no dependency on ``users``.
ADMIN_ROLE = "admin"

# Brute-force limits. Deliberately NOT settings fields: they are the only
# defence on a single shared secret and are not an operator-tunable surface.
MAX_FAILURES = 10
WINDOW_SECONDS = 300
COOLDOWN_SECONDS = 900
