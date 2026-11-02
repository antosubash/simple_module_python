"""Vite ``import.meta.glob`` patterns for a module's ``pages/`` directory.

Split out of :mod:`simple_module_hosting.manifest` so the rule about *which
files are pages* lives in one place, next to the reason it exists — the
manifest module is about writing the four generated files, not about glob
semantics.

The host's own glob is the twin of this, written by hand in
``host/client_app/pages.ts``; the two must agree on ``TEST_FILE_SUFFIXES``.
``test_manifest.py`` asserts both.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Suffixes that are tests living beside a page, never pages themselves.
#:
#: ``pages/**/*.tsx`` matched them, with two consequences: the resolver
#: registered a phantom page (``Error.test``), and Vite followed the import
#: into the production bundle — shipping the test file and dragging
#: ``@testing-library`` into a vendor chunk for every visitor to download.
TEST_FILE_SUFFIXES = ("test.tsx", "spec.tsx")


def glob_patterns(base: str) -> list[str]:
    """The include pattern for ``base`` plus one negation per test suffix.

    Every entry is anchored on the same ``base``: Vite resolves a negation
    relative to the importing file just like the include, so an exclusion
    written against a different base silently matches nothing.
    """
    return [f"{base}/**/*.tsx", *(f"!{base}/**/*.{suffix}" for suffix in TEST_FILE_SUFFIXES)]


def glob_patterns_for(pages_dir: Path, output_dir: Path) -> list[str]:
    """Build the ``import.meta.glob`` patterns relative to ``output_dir``.

    Vite 8 interprets filesystem-absolute paths against the project root, not
    the filesystem, so we always emit the path relative to the file where the
    glob lives (``modules.generated.ts`` under ``output_dir``).
    """
    try:
        rel = Path(os.path.relpath(pages_dir, output_dir.resolve()))
    except ValueError:
        # Different drive on Windows — fall back to absolute (rare).
        return glob_patterns(pages_dir.as_posix())
    rel_str = rel.as_posix()
    if not rel_str.startswith(("./", "../")):
        rel_str = "./" + rel_str
    return glob_patterns(rel_str)
