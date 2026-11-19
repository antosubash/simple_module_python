#!/bin/sh
# Container entrypoint for the default app image (see ../Dockerfile).
#
# Seed an admin and apply migrations before the app resolves its root secret.
# Once the settings table exists, the host stores a generated key and reuses it
# on later starts. An explicit SM_SECRET_KEY still wins.
set -e

# The users module seeds only while its table is empty. These credentials
# are for first boot, not a password reset for an existing volume.
: "${SM_USERS_BOOTSTRAP_EMAIL:=admin@example.com}"
if [ -z "${SM_USERS_BOOTSTRAP_PASSWORD:-}" ]; then
    SM_USERS_BOOTSTRAP_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
    export SM_USERS_BOOTSTRAP_PASSWORD_GENERATED=1
fi
export SM_USERS_BOOTSTRAP_EMAIL SM_USERS_BOOTSTRAP_PASSWORD

if [ "$SM_USERS_BOOTSTRAP_PASSWORD" = "changeme" ]; then
    if [ "${SM_ENVIRONMENT:-production}" = "production" ]; then
        echo "entrypoint: refusing SM_USERS_BOOTSTRAP_PASSWORD=changeme in production; set a secure password or leave it unset to generate one." >&2
        exit 1
    fi
    echo "entrypoint: WARNING - SM_USERS_BOOTSTRAP_PASSWORD is the public default; set a secure password before deploying." >&2
fi

# `upgrade heads` (plural) applies every per-module migration branch;
# `upgrade head` (singular) errors once a second module ships a branch label.
echo "entrypoint: applying migrations..." >&2
alembic -c host/alembic.ini upgrade heads

exec "$@"
