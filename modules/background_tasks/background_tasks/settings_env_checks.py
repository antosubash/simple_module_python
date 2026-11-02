"""Environment checks behind ``BackgroundTasksSettings``' model validators.

Kept apart from ``settings.py`` so the settings model stays a readable list of
fields. Both checks read the process environment, not the settings rows.
"""

from __future__ import annotations

import logging
import os

from simple_module_core.environments import NON_PROD_ENVIRONMENTS

from background_tasks.constants import ENV_PREFIX, ENV_REDIS_URL

logger = logging.getLogger("background_tasks.settings")


def warn_on_legacy_redis_vars(broker_url: str, result_backend: str) -> None:
    """Nudge deployments off the per-field names onto ``SM_REDIS_URL``.

    Warns rather than failing: ``smpy_gis``, ``smpy_saas``,
    ``laco_wiki_python`` and the ``nodes-k8s`` manifests all set these, and
    breaking them on upgrade buys nothing. It runs as a model validator rather
    than in the default factory because ``env_prefix`` means the env source
    answers these names before any default is consulted, so the factory never
    sees them.
    """
    for value, legacy_var in (
        (broker_url, f"{ENV_PREFIX}BROKER_URL"),
        (result_backend, f"{ENV_PREFIX}RESULT_BACKEND"),
    ):
        if os.environ.get(legacy_var) == value:
            logger.warning(
                "%s is deprecated; use %s instead (one URL seeds both the "
                "broker and the result backend).",
                legacy_var,
                ENV_REDIS_URL,
            )


def forbid_localhost_broker_in_production(broker_url: str, result_backend: str) -> None:
    """Fail boot if production is still pointed at the dev default broker.

    A localhost broker in prod means the web container is talking to its own
    6379 instead of the shared Redis service — tasks would silently queue to a
    broker no worker reads.
    """
    env = os.environ.get("SM_ENVIRONMENT", "development")
    if env in NON_PROD_ENVIRONMENTS:
        return
    bad = [
        name
        for name, url in (("broker_url", broker_url), ("result_backend", result_backend))
        if "localhost" in url or "127.0.0.1" in url
    ]
    if bad:
        names = ", ".join(bad)
        env_names = ", ".join(f"{ENV_PREFIX}{name.upper()}" for name in bad)
        raise ValueError(
            f"{names} must not point at localhost when SM_ENVIRONMENT={env!r}. "
            f"Set {ENV_REDIS_URL} on the container to the Redis service host "
            "(e.g. redis://redis:6379/0) — one URL seeds both the broker and "
            f"the result backend. ({env_names} still override it per field, "
            "but are deprecated.) These are read before the DB-backed "
            "settings exist, so an environment variable is what satisfies "
            "this at boot."
        )
