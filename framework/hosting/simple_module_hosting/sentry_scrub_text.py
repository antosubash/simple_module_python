"""Sensitive-key matching and free-text credential redaction for Sentry events.

Every pattern here runs on attacker-influenced text inside ``before_send``
(which blocks the capturing thread), so each one is linear: matches can only
start at a token boundary and every repetition near a backtracking point is
bounded, and input is capped at :data:`MAX_TEXT`
(``test_hosting_sentry_scrub_gaps`` pins both with megabyte inputs).
"""

from __future__ import annotations

import re

REDACTED = "[Filtered]"
TRUNCATED = "...[truncated]"
# The SDK no longer truncates values (``max_value_length`` is None), and the
# patterns below cost a few microseconds per character, so anything longer
# is cut before scanning: a megabyte string must not stall the request.
MAX_TEXT = 64 * 1024

# Substring words: any key containing one is sensitive, case-insensitively.
_SUBSTRING_WORDS = (
    r"passw(?:or)?d|passphrase|pwd|secret|token|authori[sz]ation|cookie|session"
    r"|api[-_]?key|csrf|xsrf|credential|private[-_]?key|signature|dsn|jwt|bearer"
    r"|credit[-_]?card|card[-_]?number"
    # client addresses are PII with send_default_pii=False
    r"|forwarded|real[-_]?ip|client[-_]?ip|remote[-_]?addr|ip[-_]?address"
)
# Short words that are only sensitive as a whole word: ``auth`` but not
# ``author``; snake_case, kebab-case and camelCase boundaries all count.
_BOUNDED_WORDS = ("auth", "pass", "otp", "pin", "sid", "sig", "ssn", "cvv", "cvc", "mfa")


def _bounded(word: str) -> str:
    title, upper = word.capitalize(), word.upper()
    return (
        rf"(?-i:(?:(?<![A-Za-z0-9])(?:{word}|{title})|(?<=[a-z0-9]){title})(?![a-z])"
        rf"|(?<![A-Za-z0-9]){upper}(?![A-Za-z]))"
    )


_SENSITIVE_WORDS = "|".join((_SUBSTRING_WORDS, *map(_bounded, _BOUNDED_WORDS)))
SENSITIVE_KEY = re.compile(_SENSITIVE_WORDS, re.IGNORECASE)
# OAuth authorization codes travel as a bare ``code`` query parameter.
_EXACT_KEYS = frozenset({"code"})
_QUERY_CODE = re.compile(r"((?:^|[?&])code=)[^&#\s]*", re.IGNORECASE)

# ``Cookie:``/``Authorization:`` header lines: everything to end of line.
_HEADER_LINE = re.compile(
    r"(?<![\w\-])(?P<key>(?:proxy-)?authori[sz]ation|(?:set-)?cookie)[ \t]*:[^\r\n]*",
    re.IGNORECASE,
)
# key=value / key: value / "key": "value" / \"key\": \"value\" (JSON in a string).
_KEY_VALUE = re.compile(
    rf"""(?P<key>(?<![\w.\-])\\?["']?[\w.\-]{{0,64}}(?:{_SENSITIVE_WORDS})[\w.\-]{{0,64}}"""
    r"""\\?["']?[ \t]{0,8}[=:][ \t]{0,8})"""
    rf"""(?!{re.escape(REDACTED)})"""
    r"""(?:(?P<quote>\\?["'])(?:(?!(?P=quote))[^\r\n]){0,4096}"""
    r"""|(?:(?:Bearer|Basic|Token|Digest)[ \t]+)?[^\s&,;"'}\]\\]+)""",
    re.IGNORECASE,
)
_SCHEME_CREDENTIAL = re.compile(
    r"\b(Bearer|Basic|Token|Digest)[ \t]+[A-Za-z0-9._~+/=\-]+", re.IGNORECASE
)
# scheme://user:pass@ (the password may itself hold ``@`` or ``/``) or user@.
_URL_USERINFO = re.compile(
    r"(?P<scheme>\b[a-z][a-z0-9+.\-]{0,30}://)"
    r"(?:[^\s:/@?#]{0,256}:[^\s?#]{0,256}|[^\s/?#@]{1,256})@",
    re.IGNORECASE,
)
_JWT = re.compile(r"(?<![\w\-])eyJ[\w\-]{6,}\.[\w\-]{6,}\.[\w\-]*")
# Bare high-entropy tokens (hex keys, token_urlsafe) with no ``token=`` in front.
_LONG_TOKEN = re.compile(r"(?<![\w\-])[\w\-]{32,}={0,2}(?![\w\-=])")
_HAS_DIGIT = re.compile(r"\d")
_HAS_LETTER = re.compile(r"[A-Za-z]")
# Not secrets: lowercase snake/kebab identifiers and dashed UUIDs.
_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:[_\-][a-z0-9]+)+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def is_sensitive_key(key: object) -> bool:
    if isinstance(key, bytes | bytearray):
        key = key.decode("utf-8", "replace")
    return isinstance(key, str) and (key.lower() in _EXACT_KEYS or bool(SENSITIVE_KEY.search(key)))


def _redact_key_value(match: re.Match[str]) -> str:
    return f"{match['key']}{match['quote'] or ''}{REDACTED}"


def _redact_long_token(match: re.Match[str]) -> str:
    token = match[0]
    if not (_HAS_DIGIT.search(token) and _HAS_LETTER.search(token)):
        return token
    if _IDENTIFIER.fullmatch(token) or _UUID.fullmatch(token):
        return token
    return REDACTED


def scrub_text(text: str) -> str:
    """Redact credentials embedded in free text."""
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + TRUNCATED
    text = _URL_USERINFO.sub(rf"\g<scheme>{REDACTED}@", text)
    text = _HEADER_LINE.sub(rf"\g<key>: {REDACTED}", text)
    text = _QUERY_CODE.sub(rf"\g<1>{REDACTED}", text)
    text = _KEY_VALUE.sub(_redact_key_value, text)
    text = _SCHEME_CREDENTIAL.sub(rf"\1 {REDACTED}", text)
    text = _JWT.sub(REDACTED, text)
    return _LONG_TOKEN.sub(_redact_long_token, text)
