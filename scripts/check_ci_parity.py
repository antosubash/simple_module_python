"""Require every `make lint` prerequisite to run in the PR workflow.

Intentional local-only checks belong in LOCAL_ONLY_CHECKS with a reason.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

import yaml

# Target -> reason. Empty because every current lint prerequisite runs in CI.
LOCAL_ONLY_CHECKS: dict[str, str] = {}
WORKFLOW = Path(".github/workflows/pr.yml")


def lint_prerequisites(makefile: str) -> set[str]:
    """Read lint rules, including continued lines and trailing comments."""
    logical = re.sub(r"\\\n", " ", makefile)
    rules = re.findall(r"^lint\s*:(.*)$", logical, re.MULTILINE)
    if not rules:
        raise ValueError("Makefile has no lint target")
    return {word for rule in rules for word in rule.split("#", 1)[0].split()}


def workflow_targets(workflow: str) -> set[str]:
    """Collect make targets from run steps; comments and step names don't count."""
    targets: set[str] = set()
    data = yaml.safe_load(workflow)
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            for line in step.get("run", "").replace("\\\n", " ").splitlines():
                lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
                lexer.whitespace_split = True
                tokens = list(lexer)
                in_make = False
                for index, token in enumerate(tokens):
                    if token in {";", "&&", "||", "|", "&", "(", ")"}:
                        in_make = False
                    elif token == "make" and (
                        index == 0 or tokens[index - 1] in {";", "&&", "||", "|", "&", "("}
                    ):
                        in_make = True
                    elif in_make and not token.startswith("-") and "=" not in token:
                        targets.add(token)
    return targets


def check_parity(root: Path) -> list[str]:
    prerequisites = lint_prerequisites((root / "Makefile").read_text(encoding="utf-8"))
    covered = workflow_targets((root / WORKFLOW).read_text(encoding="utf-8"))
    return [
        f"{target}: make lint prerequisite missing from {WORKFLOW} run steps"
        for target in sorted(prerequisites - covered - LOCAL_ONLY_CHECKS.keys())
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        errors = check_parity(args.root)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
