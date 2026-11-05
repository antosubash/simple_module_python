"""Refresh-outcome credentials are redacted from audit diffs."""

from auth.models import RefreshOutcome
from simple_module_db.audit import collect_audit_records
from sqlalchemy.orm import Session


def test_refresh_outcome_credentials_are_redacted():
    with Session() as session:
        session.add(
            RefreshOutcome(
                outcome_key="private", lock_key="private", expires_at=1, session={"token": "x"}
            )
        )
        changes = {c["field"]: c["new"] for c in collect_audit_records(session)[0].changes}
    assert {f: changes[f] for f in ("lock_key", "session")} == dict.fromkeys(
        ("lock_key", "session"), "[redacted]"
    )
