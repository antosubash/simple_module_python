#!/bin/sh
# Container entrypoint for the default app image (see ../Dockerfile).
#
# Three things have to happen before uvicorn binds, all of which the image can
# do for itself so `docker run -p 8000:8000 <image>` is enough:
#
#   1. Fill in the secrets production refuses to run without. The image ships
#      no baked-in keys (an image everyone can pull is the worst possible
#      place for one), so any that are still unset get an ephemeral random
#      value — enough to boot and log in, gone on the next start.
#   2. Seed an admin, so a bare `docker run` lands on a login you can pass
#      (admin@example.com / a generated password unless overridden).
#   3. Apply migrations. A fresh SQLite volume has no tables at all, and the
#      boot-time SM010 check fails the app in production when the DB revision
#      is behind head.
set -e

# SM_SECRET_KEY signs session cookies; the two SM_USERS_* secrets sign
# password-reset and email-verification tokens. All three reject their
# placeholder default when SM_ENVIRONMENT is a production value.
_ephemeral=""
for _var in SM_SECRET_KEY SM_USERS_RESET_PASSWORD_TOKEN_SECRET SM_USERS_VERIFICATION_TOKEN_SECRET; do
    eval "_current=\${$_var:-}"
    if [ -z "$_current" ]; then
        eval "export $_var=\"\$(python -c 'import secrets; print(secrets.token_urlsafe(48))')\""
        _ephemeral="$_ephemeral $_var"
    fi
done

if [ -n "$_ephemeral" ]; then
    echo "entrypoint: generated ephemeral secrets for:$_ephemeral" >&2
    echo "entrypoint: sessions and any reset/verification links they sign die on restart — set these to persist them." >&2
fi

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
