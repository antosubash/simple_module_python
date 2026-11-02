# Git repos as first-class module sources

**Date:** 2026-08-19
**Status:** Approved design, pre-implementation
**Owner:** Anto Subash

## Problem

Modules are documented and tooled as "installable from PyPI". The discovery
mechanism (`[project.entry-points.simple_module]`) has never cared where a
package came from, but everything above it does: the CLI catalog is a
hardcoded dict of PyPI names, the wizard only offers catalog entries,
`package-update` only understands index releases, and the docs say PyPI.

Target scenarios, in priority order:

1. **Private/internal modules** — modules that will never be on public PyPI,
   installed from a private GitHub/GitLab repo.
2. **Zero-ceremony sharing** — anyone can distribute a module by pushing a
   repo; no PyPI account, no trusted publishing, no release pipeline.
3. **Full source-agnosticism** — PyPI, git, and local path are equal citizens
   in the CLI, wizard, update flow, and docs.

Explicitly rejected directions (decided during brainstorming):

- **No registry, no taps, no extensible catalog file.** Discovery is
  "paste a URL you already know". The hardcoded catalog remains for
  first-party modules only.
- **No runtime plugin manager.** Modules are installed by the package
  manager into the environment, never by the running app.
- **No `modules.toml` manifest.** `pyproject.toml` + `uv.lock` stay the
  single source of truth.

## Why this is cheap: what already works

- **Discovery** is entry-point based; any installed distribution is found.
  `uv add git+…` already produces a working module today.
- **Frontend** is already source-agnostic: the wheel force-includes
  `package.json` and `pages/` into the Python package, and the host aliases
  each module's npm name onto its installed package directory in
  site-packages (`assets.py::find_npm_name`). No npm registry is involved in
  a host build, so a git-installed module flows through `gen-pages` and Vite
  unchanged.
- **Version truth lives in the package.** `pyproject.toml` `version`,
  `ModuleMeta.version`, and `requires_framework` are read from the installed
  package at boot — identical for PyPI and git installs.

What this design adds is therefore CLI/UX, a versioning convention, and docs
— not loader or build changes.

## Core mechanism: `[tool.uv.sources]`

A git module is declared as a **normal named dependency with a range**, plus
a source redirect:

```toml
# host pyproject.toml
dependencies = [
  "simple_module_blog>=1.2.0,<2.0",
]

[tool.uv.sources]
simple_module_blog = { git = "https://github.com/x/blog-module", tag = "v1.2.0" }
```

Properties this buys:

- uv validates that the checkout's declared version satisfies the range.
- `uv.lock` pins the exact commit SHA — reproducible even on branch refs.
- The dependency name stays abstract, so a host can re-point a module from
  git to PyPI (or a fork) without touching the dependency list.

Honest differences from PyPI, to be documented:

1. **No range resolution.** Git gives you exactly the ref you pinned; there
   is no index of versions. Tags are the release mechanism (below).
2. **Updates are explicit.** Moving to a newer version means rewriting the
   pinned tag (the update flow automates this).
3. **Branch pins are dev-mode.** `branch = "main"` re-pins only on
   `uv lock --upgrade-package`; CLI output labels branch pins as such.

## 1. `smpy add <spec>`

New top-level command. Accepted spec forms:

| Spec | Meaning |
|---|---|
| `simple_module_blog` (optional extras/range) | PyPI dependency, today's behavior |
| `git+https://host/x/repo` | git source, default branch |
| `git+https://host/x/repo@v1.2.0` | pinned tag (also accepts branch or SHA after `@`) |
| `git+…#subdirectory=modules/blog` | module inside a bigger repo |

Any git spec **without** `#subdirectory` goes through the multi-module scan
(§2), regardless of whether an `@ref` was given.
| `../path/to/module` | local path, written with `editable = true` |

Behavior for git specs:

1. **Resolve metadata first, write nothing on failure.** Shallow-clone the
   repo (`--depth 1`, at the requested ref) into a cache directory under the
   user cache home. Read the target package's `pyproject.toml` for the
   distribution name, version, and entry-point declaration.
2. **Write** the dependency (range derived from the resolved version:
   `>=<version>,<next-major>`) and the `[tool.uv.sources]` entry using
   `tomlkit`, preserving existing file formatting.
3. **Sync + regenerate:** `uv sync`, npm alias install, `gen-pages`.
4. **Validate** (§6) and print the migration reminder if the module ships
   models.

Auth for private repos is delegated entirely to git (SSH keys, credential
helpers, tokens in CI). Documented, not built.

## 2. Multi-module repos

Some repos carry several modules (monorepo `modules/` layout, e.g.
`python-modules`). `smpy add git+URL` **without** a `#subdirectory`:

- Scan the shallow clone for every directory whose `pyproject.toml` declares
  `[project.entry-points.simple_module]`.
- **One found** → add it (its directory becomes `subdirectory` unless it is
  the repo root).
- **Several found** → interactive checkbox picker (same UI as the wizard
  catalog); non-interactive via `--module blog,comments` or `--all`.
- Each selection becomes its own dependency + source entry sharing the repo
  URL, each with its own `subdirectory`.

Cross-dependencies between sibling modules resolve naturally: each sibling
declares a normal named dependency, and the host maps every sibling name to
the same repo.

## 3. Versioning convention

- **Repo-wide lockstep `v*` tags** are the documented convention — one tag
  releases every module in the repo (exactly how simple_module_python itself
  releases). The scaffolded standalone module already ships a `publish.yml`
  keyed on `v*` tags, so authors do this anyway.
- **All modules pinned from one repo share one ref.** The update flow moves
  them as a group; mixed sibling revs is a combination nobody tests.
- `requires_framework` keeps working unchanged at boot. At add/update time
  the CLI does a **warn-only** check of the module's framework dependency
  range in its `pyproject.toml` against the installed framework version.

## 4. `smpy update [name | --all]`

- **PyPI-sourced** modules delegate to `uv lock --upgrade-package <name>`.
- **Git-sourced, tag-pinned:** `git ls-remote --tags <url>`, parse `v*`
  semver tags, select the newest satisfying the host's declared range,
  rewrite the `tag =` pin — **group-wise**: every module sourced from the
  same repo moves to the same tag in one operation.
- **Git-sourced, branch-pinned:** re-lock to the newest SHA
  (`uv lock --upgrade-package`), output labeled as a dev-mode update.
- After any pin change: `uv sync` → npm aliases → `gen-pages` → validation,
  plus the migration reminder when the update introduces model changes
  (detected the same way `make doctor`'s drift check works).

## 5. Wizard / `create-host` integration

After the catalog checkbox step, the wizard asks **"Add modules from a git
URL?"** and loops: each pasted URL goes through the §2 scan/picker, and the
scaffolded host's `pyproject.toml` is written with the dependency + sources
entries. The non-interactive `create-host` gains a repeatable
`--git-module <spec>` flag with the same semantics as `smpy add`.

## 6. Validation & failure modes

- **Nothing is written until resolution succeeds.** Clone/parse failures
  leave `pyproject.toml` untouched and print the git error verbatim.
- **Missing entry point** is a hard error with the exact hint: the repo (or
  chosen subdirectory) has no `[project.entry-points.simple_module]`.
- **Post-install checks:** the entry point actually appears in the
  environment; doctor-grade diagnostics run (`SM001` missing meta, `SM008`
  duplicate name, `SM020` second auth provider, locale checks).
- **Migration reminder:** if the module ships SQLModel tables, print the
  host migration step (`make migration msg="add <module>"` / `make migrate`).
- **Security posture:** the first git add in a host prints a one-line notice
  that this installs and executes code from a URL the operator chose.
  Doctor checks validate structure, never trustworthiness.

## 7. Documentation changes

- `docs/module-authoring.md`: reframe the opening to "installable from PyPI
  **or any git repo**"; add a **Distributing via git** section covering the
  `v*` tag convention, multi-module repo layout, what a repo must contain
  (entry point, packaged `package.json`/`pages/`), and private-repo auth.
- Host-side docs (README template + guide): `smpy add` / `smpy update`
  usage, spec forms table, branch-pin caveat.
- `framework-conventions.md` gains the lockstep-tag convention if module
  authors need to rely on it.

## 8. Testing

CLI tests in `framework/cli/tests/` (globally-unique basenames, no network):

- **Fixture bare repos** built on the fly with `git init`/`commit`/`tag`
  under `tmp_path`, single- and multi-module layouts.
- Spec parsing: every form in the §1 table, including `@ref` +
  `#subdirectory` combinations and rejection of malformed specs.
- Multi-module scan: detection, picker selection set, per-module
  `subdirectory` writing.
- `tomlkit` round-trip: existing pyproject formatting/comments preserved;
  add is idempotent; failure writes nothing.
- Tag selection: semver filtering against ranges, group update moves all
  same-repo siblings, branch-pin path labeled dev-mode.
- Wizard step: scripted TTY test following existing `test_cli_wizard.py`
  patterns.

## Deferred (explicitly out of scope)

- `smpy remove` (deleting dep + source + regenerating aliases).
- Any registry, tap, or extensible catalog concept.
- npm-registry publishing for git modules (irrelevant to in-host builds;
  matters only for the out-of-tree frontend DX track, see
  `2026-08-06-out-of-tree-frontend-dx-design.md`).
- Per-module (non-lockstep) tag schemes like `blog-v1.2.0`.
