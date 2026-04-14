"""Framework exceptions."""


class ModuleError(Exception):
    """Base exception for module-related errors."""


class CircularDependencyError(ModuleError):
    """Raised when a circular dependency is detected between modules."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        path = " -> ".join(cycle)
        super().__init__(f"Circular dependency detected: {path}")


class NotFoundError(Exception):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, identifier: str | int) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} with id '{identifier}' not found")


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {errors}")
