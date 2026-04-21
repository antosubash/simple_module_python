"""SM018: flag Inertia ``router.{post,patch,put,delete}('/api/...')`` calls.

Inertia's client-side router (``@inertiajs/react``'s ``router.*``) expects
Inertia-shaped responses or redirects — a raw JSON body from the REST
API layer triggers ``All Inertia requests must receive a valid Inertia
response``. The fix is to point the call at a module **view** endpoint
that returns ``RedirectResponse(..., status_code=303)``.

This check regex-scans each module's ``pages/**/*.tsx`` files for the
anti-pattern. It is textual (not AST) because a full TSX parser in
Python is not worth the dependency — the pattern is unambiguous enough
that string matching catches it reliably.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

# Matches calls like:
#   router.post('/api/datasets/', ...)
#   router.patch(`/api/datasets/${id}`, ...)
#   router.delete("/api/datasets/" + id)
# The quote character is captured so we only match string-literal URLs
# (backtick, single, or double) — variable URLs don't count.
_ROUTER_API_CALL = re.compile(
    r"router\.(?P<method>post|patch|put|delete)\s*\(\s*[`'\"]/api/",
)


def check_inertia_api_calls(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]:
    """Warn when a page uses Inertia's router against a JSON API endpoint."""
    pages_dir = src_dir / "pages"
    if not pages_dir.exists():
        return []

    diags: list[Diagnostic] = []
    for tsx in sorted(pages_dir.rglob("*.tsx")):
        try:
            source = tsx.read_text()
        except OSError:
            continue
        for lineno, line in enumerate(source.splitlines(), start=1):
            match = _ROUTER_API_CALL.search(line)
            if not match:
                continue
            method = match.group("method").upper()
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM018",
                    message=(
                        f"router.{method.lower()}() targets a JSON API endpoint — "
                        "Inertia will reject the response"
                    ),
                    module_name=mod.meta.name,
                    file=f"{tsx}:{lineno}",
                    suggestion=(
                        "Point the call at a view endpoint (e.g. '/"
                        f"{mod.meta.name.lower()}/...') that returns "
                        "RedirectResponse(..., status_code=303). Or, if you "
                        "really need the JSON payload, use fetch() instead of "
                        "Inertia's router."
                    ),
                )
            )
    return diags
