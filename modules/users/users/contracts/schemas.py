"""Public request/response schemas for the users module."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users.schemas import CreateUpdateDictModel
from pydantic import ConfigDict, EmailStr
from sqlmodel import Field, SQLModel

MAX_BULK_INVITE_BODY_ADDRESSES = 1000
"""Hard ceiling on the address list one bulk-invite body may carry.

Distinct from ``bulk_invite.MAX_ADDRESSES`` (how many invites one submit may
actually mint): this bounds the work and the response, both of which are one
entry per submitted address."""

MAX_INVITE_MESSAGE_LENGTH = 1000
"""Ceiling on the optional note an inviter adds to a batch. Long enough for a
paragraph of context, short enough that it cannot be used to stuff arbitrary
content into outbound mail."""

USER_STATES = ("active", "unverified", "invited", "disabled")
"""What a row in the users table *is*, as one word.

Derived rather than stored: ``disabled`` beats everything, then an
unverified account is ``invited`` if an admin created it and ``unverified`` if
the person signed themselves up. Computed server-side so the list, the filter
and the status pill cannot drift apart."""

# NOTE on EmailStr: only *input* schemas (UserCreate/UserUpdate/UserInvite) use
# EmailStr — that is where an email must be format-validated. Response schemas
# (UserRead/UserListItem) use plain ``str``: their data comes straight from the
# DB (already validated on write), and FastAPI's response_model would otherwise
# re-run email-validator for every serialized user. Under load that validation
# was ~8% of total CPU on list endpoints (20 users/page) — pure waste.


class UserRead(CreateUpdateDictModel, SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    is_external: bool = False
    full_name: str | None = None
    tenant_id: str | None = None
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None


class UserCreate(CreateUpdateDictModel, SQLModel):
    email: EmailStr
    password: str
    is_active: bool | None = True
    is_superuser: bool | None = False
    is_verified: bool | None = False
    full_name: str | None = None


class UserUpdate(CreateUpdateDictModel, SQLModel):
    password: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
    full_name: str | None = None


# Admin + invite + self profile
class UserInvite(SQLModel):
    email: EmailStr
    full_name: str | None = None
    role_names: list[str] = []


class UserBulkInvite(SQLModel):
    """Invite several addresses in one submit, all sharing the same roles."""

    emails: list[str] = Field(max_length=MAX_BULK_INVITE_BODY_ADDRESSES)
    """Raw addresses, validated one at a time by the endpoint rather than by
    ``list[EmailStr]`` here: a single typo in a pasted column would otherwise
    422 the whole submit, and the caller would get an error naming a list index
    instead of the per-address outcomes this endpoint exists to report.

    The length bound is on the *body*, not the invite cap: the endpoint reports
    an outcome for every address it is handed, so an unbounded list means
    unbounded per-address validation and an equally unbounded response. Set far
    above the invite cap so the "over the limit" outcomes stay visible for any
    plausible paste."""
    role_names: list[str] = []
    message: str | None = Field(default=None, max_length=MAX_INVITE_MESSAGE_LENGTH)
    """A line of context from the inviter, added to the invite email.

    An invitation from an unfamiliar address is indistinguishable from
    phishing; "you're joining the migration project" is what makes it
    answerable. Bounded because it goes straight into a message body."""


class BulkInviteResult(SQLModel):
    """Outcome for a single address in a bulk invite.

    Per-address rather than all-or-nothing: one already-registered address in
    a pasted list of twenty should not discard the other nineteen.
    """

    email: str
    status: str
    """``"sent"`` — mail dispatched. ``"link"`` — created, but the configured
    mailer cannot deliver, so ``link`` carries the URL. ``"failed"`` — see
    ``detail``."""
    detail: str = ""
    link: str | None = None
    """One-time accept URL. Populated only when the mailer cannot deliver;
    otherwise the token stays out of the response entirely."""


class BulkInviteResponse(SQLModel):
    results: list[BulkInviteResult]


class UserAdminCreate(SQLModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role_names: list[str] = []


class UserDetailsUpdate(SQLModel):
    email: EmailStr
    full_name: str | None = None


class UserListItem(SQLModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    is_active: bool
    is_verified: bool
    is_external: bool = False
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    invited_at: datetime | None = None
    invite_expires_at: datetime | None = None
    """When the outstanding invite stops working — ``invited_at`` plus the
    verification-token lifetime. The token itself is not stored, so this is
    computed on read from the same setting that mints it."""
    state: str = "active"
    """One of :data:`USER_STATES`."""
    roles: list[str] = []


class RoleListItem(SQLModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    user_count: int = 0


class RoleAssignment(SQLModel):
    role_names: list[str]


class LoginRequest(SQLModel):
    """The sign-in form, posted url-encoded.

    Field names match ``OAuth2PasswordRequestForm`` so existing clients keep
    working; ``grant_type``/``scope``/``client_id`` are still accepted on the
    wire and ignored. ``remember`` is the "Keep me signed in" checkbox: it
    lengthens the issued credential rather than changing what is checked.
    """

    username: str
    password: str
    remember: bool = False


class AcceptInviteRequest(SQLModel):
    token: str
    password: str
    full_name: str | None = None
    """What the invitee calls themselves. Optional because an admin may have
    filled it in when minting the invite, in which case the form pre-fills and
    a blank submit must not wipe it."""


class PasswordResetLink(SQLModel):
    link: str


class SelfProfileUpdate(SQLModel):
    full_name: str | None = None


class SelfPasswordChange(SQLModel):
    """Change your own password from the profile page.

    The current password is required even though the caller already holds a
    session: an unattended browser is exactly the case this guards against,
    and it is the only proof that the person at the keyboard is the account's
    owner rather than whoever sat down next.
    """

    current_password: str
    new_password: str
