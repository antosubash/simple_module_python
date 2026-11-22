"""Purpose separation must preserve the existing OIDC HKDF format."""

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def test_derivation_is_deterministic_and_purpose_separated():
    from simple_module_core.runtime.crypto import derive_key

    label = b"simple-module/v1/users/password-reset"
    expected = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=label).derive(
        b"root-secret"
    )
    assert derive_key("root-secret", label) == expected
    assert derive_key("root-secret", label) == derive_key("root-secret", label)
    assert derive_key("root-secret", b"simple-module/v1/users/email-verification") != expected
    assert derive_key("another-root", label) != expected


@pytest.mark.parametrize("root", ["", " \t\n"])
def test_derivation_refuses_blank_root(root):
    from simple_module_core.runtime.crypto import derive_key

    with pytest.raises(ValueError, match=r"root secret.*blank"):
        derive_key(root, b"simple-module/v1/users/email-verification")
