"""Profile claim normalization shared by principals and cached identities."""


def _string_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""
