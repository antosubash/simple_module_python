"""Record the README demo GIF by driving a running dev stack with Playwright.

The flow (about 20 s): sign in, dashboard, users list, feature flags (toggle
one), branding (change the primary colour and watch the UI re-theme), doctor
panel. Playwright records a 1280x800 video; ffmpeg converts it to a GIF with a
two-pass palette (palettegen / paletteuse) at ``--width`` and ``--fps``.

Recipe (spare ports, SQLite file DB, from the repo root; see also
``.claude/skills/running-the-stack/SKILL.md``)::

    make gen-pages
    export SM_DATABASE_URL=sqlite+aiosqlite:///./demo-tmp.db
    uv run --project host alembic -c host/alembic.ini upgrade heads
    uv run smpy users create-admin --email admin@example.com \\
        --password '<choose-one>' --force
    SM_VITE_PORT=5203 npm run dev &
    SM_VITE_DEV_URL=http://localhost:5203 \\
        uv run --project host uvicorn host.main:app --port 8203 &
    curl -fsS http://localhost:8203/health        # wait until 200
    uv run python scripts/record_readme_demo.py \\
        --base-url http://localhost:8203 --email admin@example.com \\
        --password '<choose-one>'

Then kill whatever listens on the two ports and ``rm demo-tmp.db*``. Needs
``ffmpeg`` on PATH and ``uv run playwright install chromium`` once.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page, ViewportSize, sync_playwright

VIEWPORT: ViewportSize = {"width": 1280, "height": 800}
PAUSE_MS = 1000
TYPE_DELAY_MS = 50
NEW_COLOR = "#7c3aed"
ALT_COLOR = "#0f766e"  # used when the stack already holds NEW_COLOR (re-runs)
APP_NAME = "Acme Portal"
# Seconds of the raw video to drop: the first blank page load before sign-in.
TRIM_START_S = 0.6

PATH_LOGIN = "/users/login"
PATH_DASHBOARD = "/dashboard/"
PATH_USERS = "/admin/users/"
PATH_FLAGS = "/admin/feature-flags/"
PATH_BRANDING = "/admin/branding/"
PATH_DOCTOR = "/admin/doctor/"


def _pause(page: Page, ms: int = PAUSE_MS) -> None:
    page.wait_for_timeout(ms)


def _goto(page: Page, base_url: str, path: str) -> None:
    page.goto(base_url + path, wait_until="networkidle")
    _pause(page)


def step_sign_in(page: Page, base_url: str, email: str, password: str) -> None:
    page.goto(base_url + PATH_LOGIN, wait_until="networkidle")
    _pause(page, 800)
    page.get_by_label(re.compile("email", re.I)).fill("")
    page.get_by_label(re.compile("email", re.I)).press_sequentially(email, delay=TYPE_DELAY_MS)
    password_box = page.get_by_label(re.compile("password", re.I)).first
    password_box.press_sequentially(password, delay=TYPE_DELAY_MS)
    _pause(page, 500)
    page.get_by_role("button", name=re.compile("sign in|log in|login", re.I)).click()
    page.wait_for_url(re.compile(r"/(dashboard|admin)"), timeout=20_000)
    page.wait_for_load_state("networkidle")
    _pause(page)


def _nav(page: Page, name: str, path: str, base_url: str) -> None:
    """Click the sidebar link (an Inertia visit, no blank flash); else load the URL."""
    link = page.get_by_role("link", name=re.compile(rf"^{name}$", re.I)).first
    if link.count() and link.is_visible():
        link.click()
        page.wait_for_url(re.compile(re.escape(path.rstrip("/"))), timeout=15_000)
        page.wait_for_load_state("networkidle")
        _pause(page)
    else:
        _goto(page, base_url, path)


def step_dashboard(page: Page, base_url: str) -> None:
    _goto(page, base_url, PATH_DASHBOARD)
    _pause(page, 600)


def step_users(page: Page, base_url: str) -> None:
    _nav(page, "Administration", "/admin", base_url)
    _nav(page, "Users", PATH_USERS, base_url)


def step_flags(page: Page, base_url: str) -> None:
    """Flags are registered in code, so the closest 'create' is toggling one on."""
    _nav(page, "Feature flags", PATH_FLAGS, base_url)
    switches = page.get_by_role("switch")
    if switches.count() == 0:
        return
    switches.first.click()
    _pause(page, 1100)
    page.get_by_role("button", name=re.compile(r"^(enable|disable)$", re.I)).click()
    page.wait_for_load_state("networkidle")
    _pause(page, 1800)


def step_branding(page: Page, base_url: str) -> None:
    _nav(page, "Branding", PATH_BRANDING, base_url)
    name_box = page.locator("#app_name")
    name_box.click()
    name_box.press("Control+a")
    name_box.press_sequentially(APP_NAME, delay=TYPE_DELAY_MS)
    color_box = page.locator("#primary_color")
    color = ALT_COLOR if color_box.input_value().lower() == NEW_COLOR else NEW_COLOR
    color_box.click()
    color_box.press("Control+a")
    color_box.press_sequentially(color, delay=TYPE_DELAY_MS)
    color_box.blur()
    _pause(page, 1600)
    page.get_by_role("button", name=re.compile("publish", re.I)).first.click()
    page.wait_for_load_state("networkidle")
    _pause(page, 2200)


def step_doctor(page: Page, base_url: str) -> None:
    _nav(page, "Doctor", PATH_DOCTOR, base_url)
    _pause(page, 1500)


def record(base_url: str, email: str, password: str, video_dir: Path) -> Path:
    """Drive the flow and return the path of the recorded video."""
    steps: list[Callable[[Page], None]] = [
        lambda p: step_sign_in(p, base_url, email, password),
        lambda p: step_dashboard(p, base_url),
        lambda p: step_users(p, base_url),
        lambda p: step_flags(p, base_url),
        lambda p: step_branding(p, base_url),
        lambda p: step_doctor(p, base_url),
    ]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(video_dir),
            record_video_size=VIEWPORT,
            color_scheme="light",
        )
        page = context.new_page()
        for step in steps:
            step(page)
        video = page.video
        context.close()  # flushes the video file
        browser.close()
        if video is None:
            raise RuntimeError("Playwright recorded no video")
        return Path(video.path())


def to_gif(video: Path, out: Path, width: int, fps: int) -> None:
    """Two-pass ffmpeg conversion: build a palette, then dither with it."""
    out.parent.mkdir(parents=True, exist_ok=True)
    scale = f"fps={fps},scale={width}:-1:flags=lanczos"
    palette = video.with_name("palette.png")
    common = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(TRIM_START_S), "-i", str(video)]
    subprocess.run(
        [*common, "-vf", f"{scale},palettegen=stats_mode=diff", str(palette)],
        check=True,
    )
    subprocess.run(
        [
            *common,
            "-i",
            str(palette),
            "-lavfi",
            f"{scale} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
            "-loop",
            "0",
            str(out),
        ],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8203")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/assets/readme-demo.gif"))
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args(argv)

    if shutil.which("ffmpeg") is None:
        print("ffmpeg is required on PATH", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="readme-demo-") as tmp:
        video = record(args.base_url.rstrip("/"), args.email, args.password, Path(tmp))
        to_gif(video, args.out, args.width, args.fps)
    size_mb = args.out.stat().st_size / 1_048_576
    print(f"wrote {args.out} ({size_mb:.2f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
