# Publishing simple_module_python

This repo publishes **14 Python packages** to PyPI and **3 JS packages** to npm in one lockstep version bump. Releases are driven entirely from GitHub Actions — no tokens live on your laptop.

- **Python packages** (`simple_module_*`) → [pypi.org](https://pypi.org)
- **JS packages** (`@simple-module-py/*`) → [npmjs.com](https://www.npmjs.com)
- **Auth**: OIDC Trusted Publishing on PyPI; `NPM_TOKEN` on npm
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

For *each* of the 14 Python project names, on [pypi.org](https://pypi.org/manage/account/publishing/):

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
simple_module_core
simple_module_db
simple_module_hosting
simple_module_testing
simple_module_auth
simple_module_background_tasks
simple_module_dashboard
simple_module_datasets
simple_module_feature_flags
simple_module_file_storage
simple_module_permissions
simple_module_products
simple_module_settings
simple_module_users
```

> **Pending publishers**: if a project doesn't exist on PyPI yet, "pending publisher" is the right flow — you're reserving the project name *and* wiring up auth in one step. The first successful publish creates the project and promotes the pending publisher to a real one.

### 2. npm

1. On [npmjs.com](https://www.npmjs.com), sign in as the owner.
2. Create the `@simple-module-py` organization (Settings → "Create a new organization"). This is a one-time step.
3. Generate an automation-type access token with publish rights for `@simple-module-py/*`.
4. In this repo: **Settings → Secrets and variables → Actions → New repository secret**, name `NPM_TOKEN`, paste the token.

### 3. GitHub Environments

In the repo's **Settings → Environments → New environment**, create two environments — they match the `environment:` fields used by the release workflow jobs:

- `pypi`
- `npm`

No secrets or variables are needed on the `pypi` environment (OIDC). Optionally, add a **deployment-protection rule** requiring a manual approval on both so every release gets a human click before it goes live.

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

All 17 packages bump in lockstep to the same version. We follow a relaxed SemVer during the 0.x phase:

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
- `build` rewrites every version, builds 14 wheels + 14 sdists + 3 npm tarballs, and uploads them as artifacts.
- `publish-pypi` fans out 14 parallel jobs, each publishing one wheel+sdist pair via OIDC Trusted Publishing.
- `publish-npm` fans out 3 parallel jobs publishing `@simple-module-py/*` tarballs with `NPM_TOKEN`. Each job verifies the tarball's `package.json` is actually scoped to `@simple-module-py/*` before invoking `npm publish`.
- `finalize` re-applies the bump, commits `release: vX.Y.Z`, tags it, and pushes both.

Expected wall time: 5–8 minutes.

### Step 4. GitHub Release notes

The workflow creates the `vX.Y.Z` tag but not a GitHub Release. Do that manually:

1. Go to [Releases → Draft a new release](https://github.com/antosubash/simple_module_python/releases/new).
2. Pick the `vX.Y.Z` tag.
3. Title: `vX.Y.Z`.
4. Body: user-facing changes since the previous release. `gh` can autofill from commits: `gh release create vX.Y.Z --generate-notes`.

---

## Local pre-flight (optional but recommended)

Before running the workflow, you can rehearse the whole pipeline offline. Nothing leaves your machine:

```bash
# 1. Check all 17 packages are currently at 0.0.1 (or your expected base)
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
ls dist-py/ | wc -l        # expect 28 (14 wheels + 14 sdists)
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

### npm publish fails with `401 Unauthorized` or a weird git error

- `401` → `NPM_TOKEN` secret is missing, expired, or lacks publish rights on `@simple-module-py/*`. Rotate and re-run.
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

1. Add its distribution name to `scripts/bump_version.py`'s package list (should be automatic if it lives under `modules/*/pyproject.toml`).
2. Add it to `.github/workflows/release.yml` under `publish-pypi` → `strategy.matrix.package`.
3. Create the PyPI Trusted Publisher entry for its project name.
4. Add a substantive README (`check_readmes.py` will fail otherwise).

`scripts/check_metadata.py` and `scripts/check_readmes.py` run in `make lint` and will tell you what's missing.

### I need to rotate or recover the owner account

Trusted Publishing is tied to the GitHub repo, not any personal account — so a PyPI account handover is the usual account-transfer flow at the registry, not a code change. For npm, rotate `NPM_TOKEN` under the new owner. Update the "Project names" section of this doc afterward.

---

## Reference — what's published where

| Registry | Package | Source |
|---|---|---|
| PyPI | `simple_module_core` | [framework/core/](../framework/core/) |
| PyPI | `simple_module_db` | [framework/db/](../framework/db/) |
| PyPI | `simple_module_hosting` | [framework/hosting/](../framework/hosting/) — ships the `sm` / `simple-module` CLI |
| PyPI | `simple_module_testing` | [framework/testing/](../framework/testing/) — pytest plugin |
| PyPI | `simple_module_auth` | [modules/auth/](../modules/auth/) |
| PyPI | `simple_module_background_tasks` | [modules/background_tasks/](../modules/background_tasks/) |
| PyPI | `simple_module_dashboard` | [modules/dashboard/](../modules/dashboard/) |
| PyPI | `simple_module_datasets` | [modules/datasets/](../modules/datasets/) |
| PyPI | `simple_module_feature_flags` | [modules/feature_flags/](../modules/feature_flags/) |
| PyPI | `simple_module_file_storage` | [modules/file_storage/](../modules/file_storage/) |
| PyPI | `simple_module_permissions` | [modules/permissions/](../modules/permissions/) |
| PyPI | `simple_module_products` | [modules/products/](../modules/products/) — reference CRUD example |
| PyPI | `simple_module_settings` | [modules/settings/](../modules/settings/) |
| PyPI | `simple_module_users` | [modules/users/](../modules/users/) |
| npm | `@simple-module-py/ui` | [packages/ui/](../packages/ui/) |
| npm | `@simple-module-py/i18n` | [packages/i18n/](../packages/i18n/) |
| npm | `@simple-module-py/tsconfig` | [packages/tsconfig/](../packages/tsconfig/) |

## Questions

File an issue: https://github.com/antosubash/simple_module_python/issues
