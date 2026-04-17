"""Shared Base for the users module's tables.

Lives in its own module so individual entity files can import it without
triggering a package ``__init__`` cycle.
"""

from simple_module_db.base import create_module_base

Base = create_module_base("users")
