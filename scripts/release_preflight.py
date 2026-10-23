"""Block releases before publishing if any matrix project is absent from PyPI."""

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from scripts.check_metadata import parse_publish_matrix

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
PYPI_PROJECT_URL = "https://pypi.org/pypi/{name}/json"


def main() -> int:
    missing: list[str] = []
    errors: list[str] = []
    for name in parse_publish_matrix(WORKFLOW):
        try:
            with urlopen(PYPI_PROJECT_URL.format(name=name), timeout=30):
                pass
        except HTTPError as exc:
            if exc.code == 404:
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
            "The public API cannot verify pending publishers. Bootstrap these projects "
            "with their first release before retrying this existence-only preflight."
        )
    for error in errors:
        print(f"::error::{error}")
    return int(bool(missing or errors))


if __name__ == "__main__":
    raise SystemExit(main())
