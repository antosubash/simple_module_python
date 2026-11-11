"""Shipped skills link only to files the CLI wheel contains (GH #875).

`skills/` is installed as `simple_module_cli/skills/`, so a relative link that
leaves it (`../../docs/...`) points nowhere in a downstream app. Repo docs are
linked through the docs site instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILLS = Path(__file__).resolve().parents[3] / "skills"
_LINK = re.compile(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)|^\s*\[[^\]]+\]:\s*<?(\S+?)>?\s*$", re.M)


def _relative_links(skill_md: Path) -> list[str]:
    text = re.sub(r"^(```|~~~).*?^\1", "", skill_md.read_text(), flags=re.M | re.S)
    targets = [(m.group(1) or m.group(2)).split("#", 1)[0] for m in _LINK.finditer(text)]
    return [t for t in targets if t and not re.match(r"[a-z][a-z0-9+.-]*:", t, re.I)]


@pytest.mark.parametrize(
    "skill_md", sorted(_SKILLS.glob("**/*.md")), ids=lambda p: str(p.relative_to(_SKILLS))
)
def test_relative_links_stay_inside_the_shipped_skills(skill_md: Path) -> None:
    for target in _relative_links(skill_md):
        resolved = (skill_md.parent / target).resolve()
        assert resolved.is_relative_to(_SKILLS.resolve()), f"{target} leaves skills/"
        assert resolved.exists(), f"{target} does not exist"
