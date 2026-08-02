"""Centralized constants for the Catalog module."""

from __future__ import annotations

from typing import Final

MODULE_NAME: Final = "Catalog"
MODULE_PACKAGE: Final = "catalog"
LOCALE_NAMESPACE: Final = MODULE_PACKAGE

API_PREFIX: Final = "/api/catalog"
VIEW_PREFIX: Final = "/catalog"

MENU_LABEL: Final = "Catalog"
MENU_URL: Final = VIEW_PREFIX
MENU_ICON: Final = "package"
MENU_ORDER: Final = 120
MENU_GROUP: Final = "Content"

PERM_GROUP: Final = MODULE_NAME
PERM_VIEW: Final = "catalog.view"
ALL_PERMISSIONS: Final = (PERM_VIEW,)

TABLE_CATEGORY: Final = "catalog_category"
TABLE_PRODUCT: Final = "catalog_product"

STATUS_DRAFT: Final = "draft"
STATUS_ACTIVE: Final = "active"
STATUS_ARCHIVED: Final = "archived"
STATUS_VALUES: Final = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_ARCHIVED)

NAME_MAX_LENGTH: Final = 200
SLUG_MAX_LENGTH: Final = 120
SKU_MAX_LENGTH: Final = 40
STATUS_MAX_LENGTH: Final = 20
DESCRIPTION_MAX_LENGTH: Final = 1000

DEFAULT_PAGE_SIZE: Final = 20
MAX_PAGE_SIZE: Final = 100

SORT_NAME: Final = "name"
SORT_PRICE: Final = "price"
SORT_CREATED: Final = "created"
SORT_VALUES: Final = (SORT_NAME, SORT_PRICE, SORT_CREATED)

PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"
PAGE_DETAIL: Final = f"{MODULE_NAME}/Detail"
