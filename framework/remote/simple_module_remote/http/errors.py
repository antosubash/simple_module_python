"""HTTP errors and the status-to-exit-code mapping."""

EXIT_USAGE = 1
EXIT_CLIENT_ERROR = 2
EXIT_SERVER_ERROR = 3
EXIT_AUTH = 4
EXIT_NOT_FOUND = 5
EXIT_CONFLICT = 6

AUTH_STATUSES = frozenset({401, 403})
_CONFLICT_STATUSES = frozenset({409, 412})
_NOT_FOUND = 404
_SERVER_MIN = 500
ERROR_MIN = 400
OK_MIN = 200
REDIRECT_MIN = 300


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


def is_success(status: int) -> bool:
    return OK_MIN <= status < REDIRECT_MIN


def exit_code_for(status: int) -> int:
    if status in AUTH_STATUSES:
        return EXIT_AUTH
    if status == _NOT_FOUND:
        return EXIT_NOT_FOUND
    if status in _CONFLICT_STATUSES:
        return EXIT_CONFLICT
    if status == 0 or status >= _SERVER_MIN:
        return EXIT_SERVER_ERROR
    if status < OK_MIN or REDIRECT_MIN <= status < ERROR_MIN:
        # A 1xx or a leftover 3xx: the request itself has to change, the server did not fail.
        return EXIT_CLIENT_ERROR
    if status < REDIRECT_MIN:
        return EXIT_SERVER_ERROR  # a 2xx that could not be used (malformed success body)
    return EXIT_CLIENT_ERROR
