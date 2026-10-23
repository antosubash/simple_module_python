"""Gate absent PyPI projects on operator confirmation of pending publishers."""

import argparse
from collections.abc import Sequence
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from scripts.check_metadata import parse_publish_matrix

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
PYPI_PROJECT_URL = "https://pypi.org/pypi/{name}/json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pending-publishers",
        default="",
        help="Comma-separated simple_module_* names confirmed to have pending publishers",
    )
    args = parser.parse_args(argv)
    confirmed = {name.strip() for name in args.pending_publishers.split(",") if name.strip()}
    missing: list[str] = []
    errors: list[str] = []
    for name in parse_publish_matrix(WORKFLOW):
        try:
            with urlopen(PYPI_PROJECT_URL.format(name=name), timeout=30):
                pass
        except HTTPError as exc:
            if exc.code == 404:
                if name in confirmed:
                    print(f"{name}: PyPI 404 accepted; operator confirmed a pending publisher.")
                else:
                    missing.append(name)
            else:
                errors.append(f"{name}: PyPI returned HTTP {exc.code}")
        except (URLError, TimeoutError, OSError) as exc:
            errors.append(f"{name}: cannot check PyPI: {exc}")

    if missing:
        print("::error::New PyPI projects need a pending publisher; see docs/release.md:")
        for name in missing:
            print(f"  - {name}")
        print(
            "The public API cannot verify pending publishers. Register them, then list "
            "these names in the workflow pending_publishers input to confirm; "
            "see docs/release.md."
        )
    for error in errors:
        print(f"::error::{error}")
    return int(bool(missing or errors))


if __name__ == "__main__":
    raise SystemExit(main())
