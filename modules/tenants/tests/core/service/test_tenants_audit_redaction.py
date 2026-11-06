"""Invitation token hashes are redacted from audit diffs."""

from datetime import UTC, datetime

from simple_module_db.audit import collect_audit_records
from sqlalchemy.orm import Session
from tenants.models import Invitation


def test_invitation_token_hash_is_redacted():
    with Session() as session:
        session.add(
            Invitation(
                tenant_id="default",
                email="invitee@example.test",
                token_hash="private",
                expires_at=datetime.now(UTC),
            )
        )
        changes = {c["field"]: c["new"] for c in collect_audit_records(session)[0].changes}
    assert changes["token_hash"] == "[redacted]"
