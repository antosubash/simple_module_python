"""``list_migrations`` — the revision history the Doctor screen renders.

The boot check already answers "is the database at head". This answers the
other half: *which* revisions exist, which module branch each one opened, and
whether the running database has applied it.
"""

from __future__ import annotations

from simple_module_hosting.migrations import (
    list_migrations,
    resolve_head_revisions,
    script_directory,
)

_ROW_KEYS = {"id", "module", "message", "applied"}


def _known_revisions() -> set[str]:
    return {rev.revision for rev in script_directory().walk_revisions()}


class TestShape:
    def test_rows_carry_exactly_the_documented_keys(self) -> None:
        rows = list_migrations()
        assert rows, "the repository ships migrations, so this must not be empty"
        for row in rows:
            assert set(row) == _ROW_KEYS, row

    def test_every_row_is_a_real_revision_newest_first(self) -> None:
        rows = list_migrations(limit=100)
        known = _known_revisions()
        assert [row["id"] for row in rows] == [
            rev.revision for rev in script_directory().walk_revisions()
        ]
        assert {row["id"] for row in rows} <= known

    def test_the_module_column_is_the_revisions_branch_label(self) -> None:
        """Only a module's *first* migration opens a branch, so the rest report
        no module rather than a guess made from the message text."""
        rows = {row["id"]: row["module"] for row in list_migrations(limit=100)}
        labelled = {
            rev.revision: sorted(rev.branch_labels)[0]
            for rev in script_directory().walk_revisions()
            if rev.branch_labels
        }
        assert labelled, "the repository has branch-labelled migrations to check against"
        for revision, label in labelled.items():
            assert rows[revision] == label
        for revision, module in rows.items():
            assert module == labelled.get(revision, "")

    def test_the_message_is_the_revision_docstring(self) -> None:
        docs = {rev.revision: (rev.doc or "") for rev in script_directory().walk_revisions()}
        for row in list_migrations(limit=100):
            assert row["message"] == docs[row["id"]]

    def test_limit_caps_the_list(self) -> None:
        assert len(list_migrations(limit=2)) == 2


class TestAppliedStatus:
    def test_nothing_is_applied_on_a_database_that_was_never_migrated(self) -> None:
        for row in list_migrations(current_revision=None, limit=100):
            assert row["applied"] is False

    def test_everything_is_applied_when_the_database_is_at_every_head(self) -> None:
        # ``migration_status`` reports the current heads as one comma-joined
        # string, which is exactly what the Doctor view hands us.
        current = ", ".join(sorted(resolve_head_revisions()))

        for row in list_migrations(current_revision=current, limit=100):
            assert row["applied"] is True, row

    def test_ancestors_of_the_current_head_count_as_applied(self) -> None:
        """A database at one branch head has applied that branch's whole chain,
        not just the revision named in ``alembic_version``."""
        script = script_directory()
        head = sorted(resolve_head_revisions())[0]
        ancestors = {rev.revision for rev in script.iterate_revisions(head, "base")}

        rows = {
            row["id"]: row["applied"] for row in list_migrations(current_revision=head, limit=100)
        }

        assert len(ancestors) > 1, "need a branch with history for this to mean anything"
        for revision in ancestors:
            assert rows[revision] is True, revision
        for revision, applied in rows.items():
            if revision not in ancestors:
                assert applied is False, revision


class TestDegradation:
    def test_a_project_root_without_alembic_yields_no_rows(self, tmp_path) -> None:
        """A deployment shipped without ``host/`` must render an empty panel,
        not a 500."""
        assert list_migrations(project_root=tmp_path) == []

    def test_an_unknown_current_revision_is_not_fatal(self) -> None:
        """A database stamped at a revision this checkout does not have (rolled
        back code, say) still lists the history it does know."""
        rows = list_migrations(current_revision="deadbeefcafe", limit=100)

        assert rows
        assert all(row["applied"] is False for row in rows)
