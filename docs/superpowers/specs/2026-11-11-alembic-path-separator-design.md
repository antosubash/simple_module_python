# `path_separator = os` in both alembic.ini files (#872)

Alembic warns ("No path_separator found in configuration; falling back to legacy
splitting...") and splits on spaces only when `prepend_sys_path` or `version_locations`
is set (alembic/config.py). Neither of our files sets them today. But a downstream host
that adds `prepend_sys_path = %(here)s` (smpy_modules did) gets the warning on every
migration command, and a checkout path containing a space breaks.

Fix: add `path_separator = os` to `host/alembic.ini` and to the scaffold template. It
has been supported since Alembic 1.16, and our floor is 1.16.3.

Test: `framework/cli/tests/test_cli_alembic_ini.py` copies each ini into a directory
whose name has a space and sets a two-entry `prepend_sys_path`. It expects no warning
(warnings are errors) and two whole paths. It fails without the line and passes with it.
