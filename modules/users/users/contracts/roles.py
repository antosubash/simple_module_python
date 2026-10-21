"""The role table, as other modules may read it.

Users are read through the app's user directory (GH #501); roles have no such
protocol yet, so the ``permissions`` role pages read this table directly and
keep ``Users`` in their ``depends_on``. Import it from here, not from
``users.models``, so the dependency stays on the published surface.
"""

from users.models.role import Role

__all__ = ["Role"]
