"""Purpose-separated keys derived from the resolved application root secret."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_key(secret: str, info: bytes) -> bytes:
    """Derive 32 bytes with HKDF-SHA256; keep each purpose's label stable."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret.encode())
