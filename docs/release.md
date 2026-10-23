# Publishing simple_module_python

This repo publishes **22 Python packages** to PyPI and **3 JS packages** to npm in one lockstep version bump. Releases are driven entirely from GitHub Actions — no tokens live on your laptop.

- **Python packages** (`simple_module_*`) → [pypi.org](https://pypi.org)
- **JS packages** (`@simple-module-py/*`) → [npmjs.com](https://www.npmjs.com)
- **Auth**: OIDC Trusted Publishing on both PyPI and npm — no long-lived tokens
- **Entry point**: Actions → `release` → Run workflow

## TL;DR — already set up? Cut a release in 3 clicks

1. Ensure `main` is green (`make lint && make test`). The workflow re-runs the whole PR suite against the dispatched commit and refuses to build if it is red.
2. [Actions → release → Run workflow](https://github.com/antosubash/simple_module_python/actions/workflows/release.yml) → pick **bump** (`patch` / `minor` / `major`), leave **version** blank → **Run**.
3. After it finishes, write release notes on the auto-created `vX.Y.Z` tag on GitHub.

For the very first time, or if any of the above is unfamiliar, keep reading.

---

## First-time setup (once per registry account)

You need to set up Trusted Publisher entries on PyPI and npm *before* running the workflow. These entries tell each registry: "trust OIDC tokens minted by this exact GitHub Actions workflow." No tokens are exchanged — the registry validates the token's GitHub-issued claims at publish time.

### 1. PyPI

For *each* of the 22 published Python project names, on [pypi.org](https://pypi.org/manage/account/publishing/):

1. Log in as the owner account (`antosubash`).
2. Go to **Your account → Publishing** (or click "Add a new pending publisher" if the project doesn't exist yet).
3. Fill in:
   - **PyPI Project Name**: the exact name, e.g. `simple_module_core`
   - **Owner**: `antosubash`
   - **Repository name**: `simple_module_python`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
4. Save.

Use the complete `publish-pypi.strategy.matrix.package` list in
[release.yml](../.github/workflows/release.yml) as the source of truth. Every
matrix package is published, including `simple_module_audit_log` and
`simple_module_keycloak`.

> **Pending publishers**: if a project doesn't exist on PyPI yet, "pending publisher" is the right flow — you're reserving the project name *and* wiring up auth in one step. The first successful publish creates the project and promotes the pending publisher to a real one.

### 2. npm

npm publishes also use OIDC Trusted Publishing (no `NPM_TOKEN` secret). On
[npmjs.com](https://www.npmjs.com):

1. Sign in as the owner.
2. Create the `@simple-module-py` organization (Settings → "Create a new organization"). This is a one-time step.
3. For *each* of the 3 npm packages (`@simple-module-py/ui`, `/i18n`, `/tsconfig`), open the package's **Settings → Trusted Publisher** page and add a GitHub Actions publisher:
   - **Repository**: `antosubash/simple_module_python`
   - **Workflow filename**: `release.yml`
   - **Environment**: `npm`

   For a brand-new scoped package that doesn't exist yet, create it with an initial manual `npm publish` (or reserve it) before the Trusted Publisher entry can be attached.

### 3. GitHub Environments

In the repo's **Settings → Environments → New environment**, create two environments — they match the `environment:` fields used by the release workflow jobs:

- `pypi`
- `npm`

No secrets or variables are needed on either environment — both publish via OIDC. Optionally, add a **deployment-protection rule** requiring a manual approval on both so every release gets a human click before it goes live.

### 4. Branch protection

The release workflow pushes a version-bump commit + tag directly to `main`. If branch protection blocks bots, pick one:

- Add `github-actions[bot]` to the allowed-pushers list on the `main` branch protection rule, **or**
- Create a fine-grained PAT scoped to this repo's `contents: write`, store it as repo secret `RELEASE_PUSH_TOKEN` — the workflow uses it automatically if present.

---

## Cutting a release

### Step 1. Confirm `main` is green

```bash
make lint
make test
```

Both should pass locally. CI should be green on every PR into `main`.

### Step 2. Pick a version

Every workspace package bumps in lockstep to the same version — `scripts/bump_version.py` walks every `framework/*`, `modules/*`, and `packages/*` manifest. The 22 PyPI + 3 npm packages are then published. We follow a relaxed SemVer during the 0.x phase:

| Situation | Input |
|---|---|
| Bug fix, docs, internal refactor | **bump**: `patch` |
| New feature, no breaking changes | **bump**: `minor` |
| Breaking change (post-1.0) | **bump**: `major` |
| Pre-release rehearsal or specific number | **version**: e.g. `0.2.0rc1` |

The workflow derives the next version from the current `framework/core/pyproject.toml` version when you pick a bump level. If you set **version** explicitly, it overrides the bump choice. Version strings must match `^[0-9]+\.[0-9]+\.[0-9]+([.-]?(a|b|rc|alpha|beta)[0-9]*)?$`.

### Step 3. Run the release

1. Go to [Actions → release → Run workflow](https://github.com/antosubash/simple_module_python/actions/workflows/release.yml).
2. **bump**: `patch` (default), `minor`, or `major`. Leave **version** blank to use it.
3. **version**: optional — set to an explicit number (e.g. `0.2.0rc1`) to override the bump.
4. **pending_publishers**: for first uploads only, enter comma-separated `simple_module_*` names whose pending publishers you have registered and verified (e.g. `simple_module_core,simple_module_users`). Leave blank otherwise.
5. **Run workflow**.

What happens:
- `resolve` computes the final version and shares it with every downstream job.
- `checks` calls `pr.yml` (`workflow_call`) on the dispatched commit, so the `pr-checks` aggregate must be green. `build` needs it: nothing is built or published from a red commit.
- `preflight` checks every PyPI matrix project via `https://pypi.org/pypi/<name>/json`. Both publish jobs require it. A 404 blocks publishing unless that exact package name is listed in **pending_publishers**. Unconfirmed absent projects are listed with a pointer to this guide; other registry errors always block publishing. The public API cannot verify Trusted Publisher configuration or see pending publishers, so this input is your confirmation that each listed project has a correctly configured pending publisher. Its first upload through this workflow creates the project.
- `build` rewrites every version, runs `uv build --all-packages` (a wheel + sdist for every buildable workspace package) plus the 3 npm tarballs, and uploads them as artifacts.
- `publish-pypi` fans out 22 parallel jobs (the matrix package list), each filtering the artifact set down to one package and publishing its wheel+sdist pair via OIDC Trusted Publishing. Existing distributions are skipped using the publish action’s `skip-existing` option, so a retry can fill in a missing wheel or sdist.
- `publish-npm` fans out 3 parallel jobs publishing `@simple-module-py/*` tarballs via OIDC Trusted Publishing. Each job verifies the tarball's `package.json` is actually scoped to `@simple-module-py/*` before invoking `npm publish`. It queries the exact version from the tarball: HTTP 200 skips it, 404 publishes it, and any other HTTP or network error fails the job.
- `finalize` re-applies the bump (the shared `.github/actions/bump-version` action, also used by `build`), cuts the CHANGELOG, commits `release: vX.Y.Z`, tags it, and pushes both.

Expected wall time: 5–8 minutes.

### Step 4. CHANGELOG and GitHub Release notes

`finalize` enables `cut-changelog` on the shared `.github/actions/bump-version` action, which runs `scripts/cut_changelog.py X.Y.Z` before the bump commit: `## [Unreleased]` becomes `## [X.Y.Z] — YYYY-MM-DD`, a fresh empty `## [Unreleased]` is inserted above it and the compare links are updated. Re-running is a no-op once the section exists. Keep `[Unreleased]` current in every user-visible PR; whatever is there at release time is the release's notes.

The GitHub Release is created with `--notes-file` from that dated section (`scripts/cut_changelog.py X.Y.Z --notes`), falling back to `--generate-notes` only when the section is empty.

To edit the body afterwards, open the release at [Releases](https://github.com/antosubash/simple_module_python/releases) after the workflow finishes:

```bash
gh release view vX.Y.Z --json body
gh release edit vX.Y.Z --notes-file - < notes.md
```

---

## Package version vs framework API version

Two version numbers exist on purpose:

- **Package version** (`0.0.x`, lockstep). Every `simple_module_*` wheel and every `package.json` under `framework/`, `modules/` and `packages/` carries the same number, enforced by `scripts/bump_version.py` (`--check` verifies it). The root and `host/` `pyproject.toml` are not published and are not bumped.
- **Framework API version** (`FRAMEWORK_API_VERSION` in `simple_module_core/versioning.py`, currently `1.0.0`). It versions the *module contract* (`ModuleBase`, the registries, the event bus, `create_module_base`, the model mixins), independent of release cadence. Modules declare a compatible range in `ModuleMeta.requires_framework` (PEP 440, e.g. `">=1.0,<2.0"`) and boot fails on a mismatch. Bump its major only for a breaking contract change.

A test (`framework/cli/tests/test_template_requires_framework.py`) pins that the scaffolded module template's `requires_framework` contains `FRAMEWORK_API_VERSION`.

---

## Local pre-flight (optional but recommended)

Before running the workflow, rehearse in a disposable worktree. Nothing is published.
The worktree starts at `HEAD`; uncommitted changes in your original checkout are
not included and remain untouched. Run the following from the repository root:

```bash
# 0. Isolate version edits and build artifacts from your working checkout
release_checkout="$PWD"
release_rehearsal=$(mktemp -d "${TMPDIR:-/tmp}/smpy-release.XXXXXX")
git worktree add --detach "$release_rehearsal/worktree" HEAD
cd "$release_rehearsal/worktree"

# 1. Check every workspace package is currently at 0.0.1 (or your expected base)
uv run python scripts/bump_version.py 0.0.1 --check

# 2. Dry-run the bump (writes nothing, shows what would change)
uv run python scripts/bump_version.py 0.0.2 --dry-run

# 3. Actually bump inside the disposable worktree
uv run python scripts/bump_version.py 0.0.2
npm install --package-lock-only

# 4. Validate metadata + READMEs
uv run python scripts/check_metadata.py
uv run python scripts/check_readmes.py

# 5. Build everything
rm -rf dist-py dist-npm
uv build --all-packages --out-dir dist-py
mkdir -p dist-npm && for p in packages/*/; do npm pack "$p" --pack-destination dist-npm; done

# 6. Sanity-check contents
ls dist-py/ | wc -l        # expect 44 (a wheel + sdist for each of the 22 published packages)
ls dist-npm/ | wc -l       # expect 3

# 7. Discard only the rehearsal worktree, including its version edits
cd "$release_checkout"
git worktree remove --force "$release_rehearsal/worktree"
rmdir "$release_rehearsal"
```

If step 5 fails for any package, the workflow will fail the same way — fix it before dispatching.
Run step 7 even if an earlier step fails; it removes only the disposable worktree.

---

## Troubleshooting

### Workflow fails at "Trusted publisher not configured"

The PyPI project's Trusted Publisher entry is missing or mismatched. Common causes:
- Wrong workflow filename (must be exactly `release.yml`, not the full path)
- Wrong environment name (must be exactly `pypi`)
- Repository owner typo

Fix the entry on the registry, re-run the failed job.

### npm publish fails with `401`/`403` or a weird git error

- `401`/`403` → the package's npm **Trusted Publisher** entry is missing or mismatched (wrong repo, workflow filename, or environment), or the `npm` GitHub environment / `id-token: write` permission isn't wired up. Fix the entry on npm and re-run. (npm publishes via OIDC now — there is no `NPM_TOKEN` secret to rotate.)
- `git ls-remote` / `Permission denied (publickey)` → npm is mis-parsing the tarball path. This is guarded for in the workflow (the path is prefixed with `./` and the package name is verified against `@simple-module-py/<pkg>`). If you see it again, the guard has regressed.

### `git push` fails in "Commit, tag, push" step

Branch protection is blocking `github-actions[bot]`. Add the `RELEASE_PUSH_TOKEN` secret (see First-time setup → Branch protection) and re-dispatch the workflow. The token is consumed automatically when present.

### Re-running after a partial publish

Fix the failed leg's cause (for example, a mismatched Trusted Publisher), then
use **Re-run failed jobs** on the original Actions run. This keeps the resolved
version and original build artifacts. Already uploaded PyPI distributions and
exact npm versions are skipped, and only missing artifacts are published.
`finalize` still commits and tags only after every publish leg succeeds.

If a new workflow dispatch is necessary, select the same source commit and set
**version** explicitly to the partially published version. Keep the source and
artifacts unchanged: these skip checks do not compare artifact hashes and cannot
replace immutable releases. Do not yank, unpublish, or bump just to resume.

### Preflight lists new PyPI projects

The preflight lists every missing matrix project before any publish job runs.
Configure each project's pending publisher as described above, then dispatch
the release with those comma-separated names in **pending_publishers**. A pending
publisher still returns 404 until the first upload; the input explicitly confirms
you verified its configuration and allows that first release to proceed. Unlisted
404s and other registry errors still block publishing. An existing project can
still have a missing or mismatched publisher; correct that in PyPI settings if
a publish leg returns 403.

### A new module was added — how do I include it in releases?

1. Version-bumping is automatic — `scripts/bump_version.py` discovers any `modules/*/pyproject.toml`, so a new module is picked up with no edit.
2. Add it to `.github/workflows/release.yml` under `publish-pypi` → `strategy.matrix.package` (only matrix packages are published).
3. Create and verify the PyPI pending Trusted Publisher entry, then include its `simple_module_*` name in **pending_publishers** when dispatching its first release.
4. Add a substantive README (`check_readmes.py` will fail otherwise).

`scripts/check_metadata.py` and `scripts/check_readmes.py` run in `make lint` and will tell you what's missing.

### I need to rotate or recover the owner account

Trusted Publishing is tied to the GitHub repo, not any personal account — so both PyPI and npm account handovers are the usual account-transfer flow at each registry, not a code change. The Trusted Publisher entries stay valid as long as the repo, workflow filename, and environment names are unchanged. Update the "Project names" section of this doc afterward.

---

## Reference — what's published where

| Registry | Package | Source |
|---|---|---|
| PyPI | `simple_module_cli` | [framework/cli/](../framework/cli/) — ships the `smpy` / `simple-module` CLI |
| PyPI | `simple_module_core` | [framework/core/](../framework/core/) |
| PyPI | `simple_module_db` | [framework/db/](../framework/db/) |
| PyPI | `simple_module_hosting` | [framework/hosting/](../framework/hosting/) — ships the `sm-host` CLI |
| PyPI | `simple_module_inertia` | [framework/inertia/](../framework/inertia/) |
| PyPI | `simple_module_test` | [framework/testing/](../framework/testing/) — pytest plugin |
| PyPI | `simple_module_api_tokens` | [modules/api_tokens/](../modules/api_tokens/) |
| PyPI | `simple_module_audit_log` | [modules/audit_log/](../modules/audit_log/) |
| PyPI | `simple_module_auth` | [modules/auth/](../modules/auth/) |
| PyPI | `simple_module_background_tasks` | [modules/background_tasks/](../modules/background_tasks/) |
| PyPI | `simple_module_branding` | [modules/branding/](../modules/branding/) |
| PyPI | `simple_module_dashboard` | [modules/dashboard/](../modules/dashboard/) |
| PyPI | `simple_module_feature_flags` | [modules/feature_flags/](../modules/feature_flags/) |
| PyPI | `simple_module_file_storage` | [modules/file_storage/](../modules/file_storage/) |
| PyPI | `simple_module_keycloak` | [modules/keycloak/](../modules/keycloak/) |
| PyPI | `simple_module_mail` | [modules/mail/](../modules/mail/) |
| PyPI | `simple_module_permissions` | [modules/permissions/](../modules/permissions/) |
| PyPI | `simple_module_settings` | [modules/settings/](../modules/settings/) |
| PyPI | `simple_module_sharing` | [modules/sharing/](../modules/sharing/) |
| PyPI | `simple_module_site_lock` | [modules/site_lock/](../modules/site_lock/) |
| PyPI | `simple_module_tenants` | [modules/tenants/](../modules/tenants/) |
| PyPI | `simple_module_users` | [modules/users/](../modules/users/) |
| npm | `@simple-module-py/ui` | [packages/ui/](../packages/ui/) |
| npm | `@simple-module-py/i18n` | [packages/i18n/](../packages/i18n/) |
| npm | `@simple-module-py/tsconfig` | [packages/tsconfig/](../packages/tsconfig/) |

## Questions

File an issue: https://github.com/antosubash/simple_module_python/issues
