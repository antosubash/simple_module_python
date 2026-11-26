"""HTTP errors and the status-to-exit-code mapping."""

EXIT_USAGE = 1
EXIT_CLIENT_ERROR = 2
EXIT_SERVER_ERROR = 3
EXIT_AUTH = 4
EXIT_NOT_FOUND = 5
EXIT_CONFLICT = 6

_AUTH_STATUSES = frozenset({401, 403})
_CONFLICT_STATUSES = frozenset({409, 412})
_NOT_FOUND = 404
_SERVER_MIN = 500
_CLIENT_MIN = 400


class UnsafePathError(ValueError):
    """Raised when a request path or base URL could leave the environment's API."""


class ApiError(Exception):
    """A failed request. Carries the status and body only; never headers or tokens."""

    def __init__(self, status: int, body_text: str = "", message: str | None = None) -> None:
        self.status = status
        self.body_text = body_text
        self.message = message or f"HTTP {status}"
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"ApiError(status={self.status})"


def exit_code_for(status: int) -> int:
    if status in _AUTH_STATUSES:
        return EXIT_AUTH
    if status == _NOT_FOUND:
        return EXIT_NOT_FOUND
    if status in _CONFLICT_STATUSES:
        return EXIT_CONFLICT
    if status >= _SERVER_MIN or status < _CLIENT_MIN:
        return EXIT_SERVER_ERROR
    return EXIT_CLIENT_ERROR
