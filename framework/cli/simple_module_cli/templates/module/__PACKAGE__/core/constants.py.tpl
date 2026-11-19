"""Stable identifiers for the {{MODULE_NAME}} module.

Permissions, menu and routing values live here. Inertia keys are checked
against this module's discovered pages.
"""

from simple_module_core.permissions import PermissionCatalogue


class Permissions(PermissionCatalogue, group="{{MODULE_NAME}}"):
    VIEW = "{{PACKAGE_NAME}}.view"
    CREATE = "{{PACKAGE_NAME}}.create"
    EDIT = "{{PACKAGE_NAME}}.edit"
    DELETE = "{{PACKAGE_NAME}}.delete"


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
