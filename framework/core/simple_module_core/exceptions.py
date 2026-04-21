"""Framework exceptions."""


class ModuleError(Exception):
    """Base exception for module-related errors."""


class InvalidModuleError(ModuleError):
    """Raised when a discovered module fails structural validation.

    Used by strict discovery (production) to turn "missing ``meta``",
    "not a ``ModuleBase``", and entry-point load failures into boot-time
    errors rather than silently-skipped modules.
    """


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


class FrameworkVersionError(ModuleError):
    """Raised when installed modules are incompatible with the framework API version."""

    def __init__(self, framework_version: str, failures: list[tuple[str, str, str]]) -> None:
        # failures: list of (module_name, requires_framework, reason)
        self.framework_version = framework_version
        self.failures = failures
        lines = [f"  - {name}: requires '{spec}' — {reason}" for name, spec, reason in failures]
        super().__init__(
            f"Installed module(s) incompatible with framework API version {framework_version}:\n"
            + "\n".join(lines)
            + "\n\nResolution: upgrade the module(s), upgrade simple_module_core, "
            "or remove the incompatible module."
        )
