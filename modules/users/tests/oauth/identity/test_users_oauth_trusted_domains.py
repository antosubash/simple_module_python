"""Exact, normalised domain matching for trusted OAuth emails (#878)."""

import pytest
from users.oauth.identity import OAuthIdentity, email_on_domains, normalize_domain

_DOMAINS = frozenset({"iiasa.ac.at", "xn--bcher-kva.example"})


@pytest.mark.parametrize(
    "email, expected",
    [
        ("jane@iiasa.ac.at", True),
        ("Jane@IIASA.AC.AT", True),
        ("jane@bücher.example", True),
        ("jane@mail.iiasa.ac.at", False),
        ("jane@iiasa.ac.at.evil.com", False),
        ("jane@notiiasa.ac.at", False),
        ("jane@other.org", False),
        ("a@b@iiasa.ac.at", False),
        ("", False),
        (None, False),
    ],
)
def test_email_on_domains_is_exact(email, expected):
    assert email_on_domains(email, _DOMAINS) is expected


@pytest.mark.parametrize("bad", ["", "*.iiasa.ac.at", ".iiasa.ac.at", "a@iiasa.ac.at", " "])
def test_normalize_domain_refuses_non_domains(bad):
    with pytest.raises(ValueError):
        normalize_domain(bad)


def test_normalize_domain_lowercases_and_encodes():
    assert normalize_domain(" Bücher.Example. ") == "xn--bcher-kva.example"


def test_trusting_marks_only_a_listed_domain_verified():
    identity = OAuthIdentity("1", "jane@iiasa.ac.at", False)
    assert identity.trusting(_DOMAINS).email_verified is True
    other = OAuthIdentity("1", "jane@other.org", False)
    assert other.trusting(_DOMAINS) is other
