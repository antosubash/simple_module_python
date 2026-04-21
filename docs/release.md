# Cutting a release

This repo publishes **14 Python packages** to PyPI and **3 JS packages** to npm in one lockstep bump. Releases are driven entirely from GitHub Actions — no tokens live on your laptop.

## One-time setup

### PyPI + TestPyPI

For every one of the 14 project names below, log into [pypi.org](https://pypi.org) (and [test.pypi.org](https://test.pypi.org)) and add a **Trusted Publisher**:

- Owner: `antosubash`
- Repository: `simple_module_python`
- Workflow filename: `release.yml`
- Environment: `pypi` (on pypi.org) or `testpypi` (on test.pypi.org)

Project names:

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

If a project name isn't yet on PyPI, create a **pending publisher** — click "publishing" in the account settings and use "Add a new pending publisher".

### npm

- Create the `@simple-module-py` scope (org) on npmjs.com if it does not exist. Owner account: `antosubash`.
- For each of `@simple-module-py/ui`, `@simple-module-py/i18n`, `@simple-module-py/tsconfig`, go to the package settings → "Trusted Publishers" (or "pending publishers" pre-first-publish) and add a GitHub Actions publisher:
  - Repository: `antosubash/simple_module_python`
  - Workflow filename: `release.yml`
  - Environment: `npm`

### GitHub Environments

In the repo's Settings → Environments, create three environments:

- `pypi`
- `testpypi`
- `npm`

No secrets are required — Trusted Publishing uses OIDC tokens. You *may* add a deployment-protection rule requiring a manual approval on `pypi` and `npm` to double-check every release.

### Branch protection bump

The release workflow pushes a version-bump commit directly to `main`. If branch protection blocks bots, either:

1. Add the `github-actions[bot]` to the allowed-pushers list, or
2. Create a fine-grained PAT scoped to this repo's contents and store it as `RELEASE_PUSH_TOKEN` — the workflow uses it if present.

## Cutting a release

1. Ensure `main` is green (`make lint && make test`).
2. Decide the version — all releases bump in lockstep. The first public release is `0.0.1`; subsequent releases are `0.0.2`, `0.0.3`, etc. unless a breaking change justifies `0.1.0`.
3. **Rehearse on TestPyPI** (recommended for every non-patch release):
   - Go to Actions → "release" → "Run workflow".
   - Version: e.g. `0.0.2a0` (PEP 440 alpha — doesn't collide with the real release).
   - Target: `testpypi`.
   - Run. The npm publish jobs are skipped on TestPyPI; inspect the uploaded npm tarball artifacts in the workflow run to confirm they look right.
4. **Real release**:
   - Actions → "release" → "Run workflow".
   - Version: e.g. `0.0.2`.
   - Target: `pypi`.
   - Run. Publishes to PyPI *and* npm, then runs the smoke app build.
5. Create/edit a GitHub Release on the new tag (the workflow doesn't create one automatically — PyPI and npm already have the tarballs; the Release is for human-facing notes).

## Cross-registry partial publish

If PyPI publishes succeed but npm publishes fail (or vice versa), the release is partial. PyPI does not allow re-uploading a version; npm permits unpublish within 72 hours.

**Procedure for partial publish:**

1. Yank the uploaded PyPI versions via the PyPI project UI (do NOT rewrite a version number).
2. If npm succeeded, `npm unpublish @simple-module-py/<pkg>@<version>` within 72h.
3. Fix the underlying cause (usually Trusted Publisher config).
4. Bump to the next patch version and re-run the workflow.

This is the accepted cost of the registries' immutability. The TestPyPI rehearsal is the mitigation — run it first.

## Questions

File an issue at https://github.com/antosubash/simple_module_python/issues.
