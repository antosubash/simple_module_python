"""Read-side listing queries of :class:`SettingService`, split out for size."""

from __future__ import annotations

from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from settings._row_masking import out
from settings.constants import (
    ALL_SCOPES,
    DEFAULT_PER_PAGE,
    SCOPE_ALL,
    SYSTEM_SCOPE_ID,
)
from settings.contracts.schemas import SettingOut, SettingScope
from settings.models import Setting


class SettingListing:
    """Mixin: the ``list_*`` / ``count_by_scope`` queries. Needs ``self.db``."""

    db: AsyncSession

    # ── Listing ─────────────────────────────────────────────────────

    async def list_all(self) -> list[SettingOut]:
        result = await self.db.execute(
            select(Setting).order_by(Setting.scope, Setting.scope_id, Setting.key)
        )
        return [out(row) for row in result.scalars()]

    async def list_filtered(
        self,
        scope: SettingScope | None = None,
        q: str | None = None,
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> tuple[list[SettingOut], int]:
        """One page of rows plus the unpaged total for the same filters.

        The browse screen used to receive every row and filter in the browser,
        which made the payload, the render and find-in-page all scale with the
        whole table instead of with what was asked for. ``q`` matches the key
        only — the search box says "Search keys…", and quietly matching values
        would surface rows whose key has nothing to do with the query.
        """
        conditions = self._filter_conditions(scope, q)
        total = await self.db.scalar(select(func.count()).select_from(Setting).where(*conditions))
        stmt = (
            select(Setting)
            .where(*conditions)
            .order_by(Setting.scope, Setting.scope_id, Setting.key)
            .offset(max(page - 1, 0) * per_page)
            .limit(per_page)
        )
        result = await self.db.execute(stmt)
        return [out(row) for row in result.scalars()], int(total or 0)

    async def count_by_scope(self, q: str | None = None) -> dict[str, int]:
        """Per-scope tallies for the filter tabs, plus ``all``.

        Every scope is named even at zero: a tab that disappears when its count
        drops to nothing moves the other tabs under the cursor mid-search.
        The scope filter itself is deliberately not applied — the tabs describe
        what each of them *would* show, so selecting one must not zero the rest.
        """
        conditions = self._filter_conditions(None, q)
        stmt = select(Setting.scope, func.count()).where(*conditions).group_by(Setting.scope)
        result = await self.db.execute(stmt)
        tallies = {str(scope): int(count) for scope, count in result.all()}
        counts = {name: tallies.get(name, 0) for name in ALL_SCOPES}
        return {SCOPE_ALL: sum(counts.values()), **counts}

    @staticmethod
    def _filter_conditions(scope: SettingScope | None, q: str | None) -> list:
        conditions = []
        if scope is not None:
            conditions.append(Setting.scope == scope.value)
        needle = (q or "").strip()
        if needle:
            # Setting keys are full of underscores, and `_` is a LIKE wildcard:
            # unescaped, a search for "smtp_host" also matches "smtpXhost", and
            # a stray "%" matches the entire table. ``ilike`` is emulated by
            # SQLAlchemy on SQLite (lower() on both sides), so one expression
            # is case-insensitive on both databases.
            conditions.append(
                Setting.key.ilike(like_contains_pattern(needle), escape=LIKE_ESCAPE_CHAR)
            )
        return conditions

    async def list_by_scope(
        self, scope: SettingScope, scope_id: str = SYSTEM_SCOPE_ID
    ) -> list[SettingOut]:
        result = await self.db.execute(self._scope_stmt(scope, scope_id))
        return [out(row) for row in result.scalars()]

    async def list_by_scope_unmasked(
        self, scope: SettingScope, scope_id: str = SYSTEM_SCOPE_ID
    ) -> list[SettingOut]:
        """The same rows with their real values, for code that *applies* them.

        The masking in :func:`_out` is for the screens. Hydration is not a
        screen: ``SettingsStore`` feeds these values back into the live module
        settings objects at boot, so a masked read writes a row of dots over the
        real secret — a mailer that cannot authenticate, and a
        ``reset_password_token_secret`` that no longer verifies the tokens it
        signed. This is the one read that must see through the mask, and it is
        spelled out rather than reached by passing a flag so that every caller
        of it is one grep away.
        """
        result = await self.db.execute(self._scope_stmt(scope, scope_id))
        return [SettingOut.model_validate(row) for row in result.scalars()]

    @staticmethod
    def _scope_stmt(scope: SettingScope, scope_id: str):
        return (
            select(Setting)
            .where(Setting.scope == scope.value, Setting.scope_id == scope_id)
            .order_by(Setting.key)
        )
