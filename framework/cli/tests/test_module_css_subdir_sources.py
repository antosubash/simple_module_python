"""uv's .venv/.gitignore hides subdirectories from Tailwind, so each gets its own @source (#419)."""

from __future__ import annotations

from simple_module_hosting.assets import ModuleAssets, render_modules_css


def _wheel(tmp_path, **overrides):
    defaults = {
        "name": "Pagebuilder",
        "package_name": "pagebuilder",
        "package_dir": tmp_path / "pagebuilder",
        "pages_dir": None,
        "theme_css": None,
        "styles_css": None,
    }
    return ModuleAssets(**{**defaults, **overrides})


def test_each_subdirectory_with_sources_gets_its_own_line(tmp_path):
    components = tmp_path / "pagebuilder" / "components"
    (components / "widgets" / "quote").mkdir(parents=True)
    (components / "Root.tsx").write_text("")
    (components / "widgets" / "Gallery.tsx").write_text("")
    (components / "widgets" / "quote" / "Quote.tsx").write_text("")
    (components / "empty").mkdir()
    (components / "__pycache__").mkdir()
    (components / "__pycache__" / "x.ts").write_text("")

    css = render_modules_css(
        [_wheel(tmp_path, components_dir=components)], in_repo=lambda _p: False
    )

    lines = [line for line in css.splitlines() if line.startswith("@source")]
    assert lines == [
        f'@source "{components.as_posix()}/**/*.{{ts,tsx}}";',
        f'@source "{(components / "widgets").as_posix()}/**/*.{{ts,tsx}}";',
        f'@source "{(components / "widgets" / "quote").as_posix()}/**/*.{{ts,tsx}}";',
    ]


def test_in_repo_module_subdirectories_get_nothing(tmp_path):
    components = tmp_path / "local" / "components"
    (components / "widgets").mkdir(parents=True)
    (components / "widgets" / "A.tsx").write_text("")
    css = render_modules_css([_wheel(tmp_path, components_dir=components)], in_repo=lambda _p: True)
    assert "@source" not in css
