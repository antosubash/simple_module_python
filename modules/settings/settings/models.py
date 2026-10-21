"""SQLModel tables for the Settings module.

``Setting`` moved to ``simple_module_db.stored_settings`` (#500) so the
framework owns the table it reads at boot. Re-exported here: it is the same
class object, never a second mapping of ``settings_setting``.
"""

from __future__ import annotations

from simple_module_db.stored_settings import Base, Setting

__all__ = ["Base", "Setting"]
