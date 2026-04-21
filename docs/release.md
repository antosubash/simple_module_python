# Publishing simple_module_python

This repo publishes **14 Python packages** to PyPI and **3 JS packages** to npm in one lockstep version bump. Releases are driven entirely from GitHub Actions — no tokens live on your laptop.

- **Python packages** (`simple_module_*`) → [pypi.org](https://pypi.org)
- **JS packages** (`@simple-module-py/*`) → [npmjs.com](https://www.npmjs.com)
- **Auth**: OIDC Trusted Publishing on both registries — no API tokens stored anywhere
- **Entry point**: Actions → `release` → Run workflow

## TL;DR — already set up? Cut a release in 3 clicks

1. Ensure `main` is green (`make lint && make test`).
2. [Actions → release → Run workflow](https://github.com/antosubash/simple_module_python/actions/workflows/release.yml) → version `X.Y.Z`, target `pypi` → **Run**.
3. After it finishes, write release notes on the auto-created `vX.Y.Z` tag on GitHub.

For the very first time, or if any of the above is unfamiliar, keep reading.

---

## First-time setup (once per registry account)

You need to set up Trusted Publisher entries on PyPI, TestPyPI, and npm *before* running the workflow. These entries tell each registry: "trust OIDC tokens minted by this exact GitHub Actions workflow." No tokens are exchanged — the registry validates the token's GitHub-issued claims at publish time.

### 1. PyPI (and TestPyPI)

For *each* of the 14 Python project names, on *both* [pypi.org](https://pypi.org/manage/account/publishing/) and [test.pypi.org](https://test.pypi.org/manage/account/publishing/):

1. Log in as the owner account (`antosubash`).
2. Go to **Your account → Publishing** (or click "Add a new pending publisher" if the project doesn't exist yet).
3. Fill in:
   - **PyPI Project Name**: the exact name, e.g. `simple_module_core`
   - **Owner**: `antosubash`
   - **Repository name**: `simple_module_python`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi` on pypi.org, `testpypi` on test.pypi.org
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
3. For each of `@simple-module-py/ui`, `@simple-module-py/i18n`, `@simple-module-py/tsconfig`:
   - Go to the package settings (or "Add a pending publisher" if unpublished).
   - Under **Trusted Publishers**, add a GitHub Actions publisher:
     - **Repository**: `antosubash/simple_module_python`
     - **Workflow name**: `release.yml`
     - **Environment name**: `npm`
4. Save.

### 3. GitHub Environments

In the repo's **Settings → Environments → New environment**, create three environments — they match the `environment:` fields used by the release workflow jobs:

- `pypi`
- `testpypi`
- `npm`

No secrets or variables are needed. Optionally, add a **deployment-protection rule** requiring a manual approval on `pypi` and `npm` so every release gets a human click before it goes live.

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

Both should pass locally. CI should be green on `main` too.

### Step 2. Pick a version

All 17 packages bump in lockstep to the same version. We follow a relaxed SemVer during the 0.x phase:

| Situation | Bump |
|---|---|
| Bug fix, docs, internal refactor | `0.0.N` → `0.0.N+1` |
| New feature, no breaking changes | `0.0.N` → `0.1.0` |
| Breaking change (post-1.0) | `X.Y.Z` → `X+1.0.0` |
| Pre-release rehearsal | append `a0`, `b1`, `rc1` (PEP 440) |

Version strings must match `^[0-9]+\.[0-9]+\.[0-9]+([.-]?(a|b|rc|alpha|beta)[0-9]*)?$` — the workflow validates this up front.

### Step 3. Rehearse on TestPyPI (recommended for anything bigger than a patch)

1. Go to [Actions → release → Run workflow](https://github.com/antosubash/simple_module_python/actions/workflows/release.yml).
2. **Version**: e.g. `0.0.2a0` (PEP 440 alpha — doesn't collide with the real release).
3. **Target**: `testpypi`.
4. Click **Run workflow**.

The rehearsal:
- Bumps all 17 packages to the alpha version, commits, and pushes a tag.
- Publishes Python wheels to [test.pypi.org](https://test.pypi.org).
- Skips npm publishes (npm has no equivalent test registry — we rely on the dry-run tarballs uploaded as workflow artifacts).
- Skips the smoke test (TestPyPI can't resolve the full dep tree).

Download the `dist-npm` artifact from the workflow run and `tar tf` a tarball to confirm the JS package contents look right. If anything's off, fix on a PR, merge, and rehearse again with `0.0.2a1`.

### Step 4. Real release

Same form, two fields changed:

1. **Version**: `0.0.2` (the real one).
2. **Target**: `pypi`.
3. **Run workflow**.

What happens:
- `bump-and-build` rewrites every version, commits `release: v0.0.2`, tags `v0.0.2`, pushes both, builds 14 wheels + 14 sdists + 3 npm tarballs.
- `publish-pypi` fans out 14 parallel jobs, each publishing one wheel+sdist pair via OIDC.
- `publish-npm` fans out 3 parallel jobs publishing via OIDC with `--provenance`.
- `smoke` installs `simple_module_hosting==0.0.2` from PyPI, runs `simple-module new smoke-app`, and runs the scaffolded app's tests against the just-published registries.

Expected wall time: 5–8 minutes.

### Step 5. GitHub Release notes

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

# 6. Sanity-check wheel contents
ls dist-py/ | wc -l        # expect 28 (14 wheels + 14 sdists)
ls dist-npm/ | wc -l       # expect 3

# 7. Revert (if you don't actually want to release)
git reset --hard HEAD~1
```

If step 5 fails for any package, the workflow will fail the same way — fix it before dispatching.

---

## Troubleshooting

### Workflow fails at "Trusted publisher not configured"

The project's Trusted Publisher entry is missing or mismatched. Common causes:
- Wrong workflow filename (must be exactly `release.yml`, not the full path)
- Wrong environment name (must be exactly `pypi` / `testpypi` / `npm`)
- Repository owner typo

Fix the entry on the registry, re-run the failed job.

### `git push` fails in "Commit, tag, and push" step

Branch protection is blocking `github-actions[bot]`. Add the `RELEASE_PUSH_TOKEN` secret (see First-time setup → Branch protection) and re-dispatch the workflow. The token is consumed automatically when present.

### PyPI publishes succeeded, npm publishes failed (partial release)

PyPI is immutable — you cannot re-upload `0.0.2` under any circumstance. Options:

1. **Yank** the bad PyPI versions via the PyPI project UI (doesn't delete, but hides them from `pip install`).
2. **Unpublish** the good npm versions within 72 hours: `npm unpublish @simple-module-py/<pkg>@0.0.2` for each.
3. Fix the root cause (almost always a Trusted Publisher misconfiguration).
4. Bump to `0.0.3` and re-run.

The TestPyPI rehearsal in Step 3 is the mitigation — do it for anything you're unsure about.

### Smoke job fails with "package not found"

PyPI has a short CDN propagation delay (typically <1 min, occasionally up to 10). The smoke job can race against it. Re-run just the smoke job from the Actions UI after a minute or two.

### A new module was added — how do I include it in releases?

1. Add its distribution name to `scripts/bump_version.py`'s package list (should be automatic if it lives under `modules/*/pyproject.toml`).
2. Add it to `.github/workflows/release.yml` under `publish-pypi` → `strategy.matrix.package`.
3. Create the PyPI (and TestPyPI) Trusted Publisher entry for its project name.
4. Add a substantive README (`check_readmes.py` will fail otherwise).

`scripts/check_metadata.py` and `scripts/check_readmes.py` run in `make lint` and will tell you what's missing.

### I need to rotate or recover the owner account

Trusted Publishing is tied to the GitHub repo, not any personal account — so a PyPI/npm account handover is the usual account-transfer flow at the registry, not a code change. Just update the "Project names" section of this doc afterward.

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
