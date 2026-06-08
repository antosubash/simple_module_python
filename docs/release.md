# Publishing simple_module_python

This repo publishes **13 Python packages** to PyPI and **3 JS packages** to npm in one lockstep version bump. Releases are driven entirely from GitHub Actions — no tokens live on your laptop.

- **Python packages** (`simple_module_*`) → [pypi.org](https://pypi.org)
- **JS packages** (`@simple-module-py/*`) → [npmjs.com](https://www.npmjs.com)
- **Auth**: OIDC Trusted Publishing on both PyPI and npm — no long-lived tokens
- **Entry point**: Actions → `release` → Run workflow

## TL;DR — already set up? Cut a release in 3 clicks

1. Ensure `main` is green (`make lint && make test`).
2. [Actions → release → Run workflow](https://github.com/antosubash/simple_module_python/actions/workflows/release.yml) → pick **bump** (`patch` / `minor` / `major`), leave **version** blank → **Run**.
3. After it finishes, write release notes on the auto-created `vX.Y.Z` tag on GitHub.

For the very first time, or if any of the above is unfamiliar, keep reading.

---

## First-time setup (once per registry account)

You need to set up Trusted Publisher entries on PyPI and npm *before* running the workflow. These entries tell each registry: "trust OIDC tokens minted by this exact GitHub Actions workflow." No tokens are exchanged — the registry validates the token's GitHub-issued claims at publish time.

### 1. PyPI

For *each* of the 13 published Python project names, on [pypi.org](https://pypi.org/manage/account/publishing/):

1. Log in as the owner account (`antosubash`).
2. Go to **Your account → Publishing** (or click "Add a new pending publisher" if the project doesn't exist yet).
3. Fill in:
   - **PyPI Project Name**: the exact name, e.g. `simple_module_core`
   - **Owner**: `antosubash`
   - **Repository name**: `simple_module_python`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
4. Save.

Repeat for every project in this list:

```
simple_module_cli
simple_module_core
simple_module_db
simple_module_hosting
simple_module_test
simple_module_auth
simple_module_background_tasks
simple_module_dashboard
simple_module_feature_flags
simple_module_file_storage
simple_module_permissions
simple_module_settings
simple_module_users
```

(`simple_module_audit_log` and `simple_module_keycloak` live in the workspace and
get version-bumped, but are **not** in the `publish-pypi` matrix — they are not
published to PyPI.)

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

Every workspace package bumps in lockstep to the same version — `scripts/bump_version.py` walks every `framework/*`, `modules/*`, and `packages/*` manifest (so the two unpublished modules, `audit_log` and `keycloak`, stay in sync too). Only the 13 PyPI + 3 npm packages are then published. We follow a relaxed SemVer during the 0.x phase:

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
4. **Run workflow**.

What happens:
- `resolve` computes the final version and shares it with every downstream job.
- `build` rewrites every version, runs `uv build --all-packages` (a wheel + sdist for every buildable workspace package) plus the 3 npm tarballs, and uploads them as artifacts.
- `publish-pypi` fans out 13 parallel jobs (the matrix package list), each filtering the artifact set down to one package and publishing its wheel+sdist pair via OIDC Trusted Publishing.
- `publish-npm` fans out 3 parallel jobs publishing `@simple-module-py/*` tarballs via OIDC Trusted Publishing. Each job verifies the tarball's `package.json` is actually scoped to `@simple-module-py/*` before invoking `npm publish`.
- `finalize` re-applies the bump, commits `release: vX.Y.Z`, tags it, and pushes both.

Expected wall time: 5–8 minutes.

### Step 4. GitHub Release notes

The `finalize` job pushes the `vX.Y.Z` tag and a follow-up step (`gh release create "v${VERSION}" --title "v${VERSION}" --generate-notes`) automatically creates a GitHub Release with autofilled notes from the commits since the previous tag.

If you want to edit the body, open the draft at [Releases](https://github.com/antosubash/simple_module_python/releases) and tweak it after the workflow finishes. To regenerate the auto-notes locally:

```bash
gh release view vX.Y.Z --json body
gh release edit vX.Y.Z --notes-file - < notes.md
```

---

## Local pre-flight (optional but recommended)

Before running the workflow, you can rehearse the whole pipeline offline. Nothing leaves your machine:

```bash
# 1. Check every workspace package is currently at 0.0.1 (or your expected base)
uv run python scripts/bump_version.py 0.0.1 --check

# 2. Dry-run the bump (writes nothing, shows what would change)
uv run python scripts/bump_version.py 0.0.2 --dry-run

# 3. Actually bump (commit on a throwaway branch if you want to keep it)
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
ls dist-py/ | wc -l        # expect 30 (a wheel + sdist for each of the 15 buildable packages; only 13 are later published)
ls dist-npm/ | wc -l       # expect 3

# 7. Revert (if you don't actually want to release)
git reset --hard HEAD~1
```

If step 5 fails for any package, the workflow will fail the same way — fix it before dispatching.

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

### PyPI publishes succeeded, npm publishes failed (partial release)

PyPI is immutable — you cannot re-upload `0.0.2` under any circumstance. Options:

1. **Yank** the bad PyPI versions via the PyPI project UI (doesn't delete, but hides them from `pip install`).
2. **Unpublish** the good npm versions within 72 hours: `npm unpublish @simple-module-py/<pkg>@0.0.2` for each.
3. Fix the root cause.
4. Bump to `0.0.3` and re-run.

### A new module was added — how do I include it in releases?

1. Version-bumping is automatic — `scripts/bump_version.py` discovers any `modules/*/pyproject.toml`, so a new module is picked up with no edit.
2. Add it to `.github/workflows/release.yml` under `publish-pypi` → `strategy.matrix.package` (only matrix packages are published; that's how `audit_log`/`keycloak` stay unpublished).
3. Create the PyPI Trusted Publisher entry for its project name.
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
| PyPI | `simple_module_test` | [framework/testing/](../framework/testing/) — pytest plugin |
| PyPI | `simple_module_auth` | [modules/auth/](../modules/auth/) |
| PyPI | `simple_module_background_tasks` | [modules/background_tasks/](../modules/background_tasks/) |
| PyPI | `simple_module_dashboard` | [modules/dashboard/](../modules/dashboard/) |
| PyPI | `simple_module_feature_flags` | [modules/feature_flags/](../modules/feature_flags/) |
| PyPI | `simple_module_file_storage` | [modules/file_storage/](../modules/file_storage/) |
| PyPI | `simple_module_permissions` | [modules/permissions/](../modules/permissions/) |
| PyPI | `simple_module_settings` | [modules/settings/](../modules/settings/) |
| PyPI | `simple_module_users` | [modules/users/](../modules/users/) |
| npm | `@simple-module-py/ui` | [packages/ui/](../packages/ui/) |
| npm | `@simple-module-py/i18n` | [packages/i18n/](../packages/i18n/) |
| npm | `@simple-module-py/tsconfig` | [packages/tsconfig/](../packages/tsconfig/) |

## Questions

File an issue: https://github.com/antosubash/simple_module_python/issues
