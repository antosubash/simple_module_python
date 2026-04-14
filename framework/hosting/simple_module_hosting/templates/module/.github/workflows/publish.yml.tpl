# Publish simple-module-{{MODULE_SLUG}} to PyPI on tagged releases.
#
# Setup (one-time, in the PyPI project settings → "Publishing"):
#   1. Create the project on https://pypi.org/manage/account/publishing/
#      with: PyPI project name = simple-module-{{MODULE_SLUG}}
#            Owner             = <your GitHub org/user>
#            Repository name   = <this repo's name>
#            Workflow filename = publish.yml
#            Environment       = pypi   (optional but recommended)
#   2. In GitHub: Settings → Environments → New environment "pypi"
#      with required reviewers if you want a manual approval gate.
#
# After setup, pushing a tag like `v0.1.0` builds the wheel + sdist and
# uploads via OIDC — no API token needs to exist anywhere.

name: Publish

on:
  push:
    tags:
      - "v*"

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write  # required for PyPI trusted publishing
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: latest

      - name: Set up Python
        run: uv python install 3.12

      - name: Install project + dev deps
        run: uv sync --extra dev

      - name: Run tests
        run: uv run pytest

      - name: Build distribution
        run: uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
