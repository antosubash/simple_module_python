"""Stable identifiers for the {{MODULE_NAME}} module.

Permissions, Inertia page keys, menu and routing values live here so the
hardcoded-strings check can hold every other file to named constants.
"""

LOCALE_NAMESPACE = "{{PACKAGE_NAME}}"

PERM_{{PACKAGE_NAME_UPPER}}_VIEW = "{{PACKAGE_NAME}}.view"
PERM_{{PACKAGE_NAME_UPPER}}_CREATE = "{{PACKAGE_NAME}}.create"
PERM_{{PACKAGE_NAME_UPPER}}_EDIT = "{{PACKAGE_NAME}}.edit"
PERM_{{PACKAGE_NAME_UPPER}}_DELETE = "{{PACKAGE_NAME}}.delete"
PERM_GROUP = "{{MODULE_NAME}}"

PAGE_BROWSE = "{{MODULE_NAME}}/Browse"
PAGE_CREATE = "{{MODULE_NAME}}/Create"
PAGE_EDIT = "{{MODULE_NAME}}/Edit"

API_PREFIX = "/api/{{MODULE_SLUG}}"
VIEW_PREFIX = "/{{MODULE_SLUG}}"

MENU_LABEL = "{{MODULE_NAME}}"
MENU_LABEL_KEY = "{{PACKAGE_NAME}}.nav.title"
# Trailing slash: the browse route is registered at "/" under the view
# prefix, so linking to the bare prefix costs a 307 on every navigation.
MENU_URL = "/{{MODULE_SLUG}}/"
MENU_ICON = "box"
MENU_ORDER = 50

# All modules share one schema, so the table name carries the module prefix.
TABLE_{{SINGULAR_UPPER}} = "{{PACKAGE_NAME}}_{{SINGULAR}}"

NAME_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000

NOT_FOUND_DETAIL = "{{SINGULAR_CLASS}} not found"
