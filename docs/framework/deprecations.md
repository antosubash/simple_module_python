# Deprecations

Every compat shim carries a removal release and the test suite enforces it (#515).

```python
from simple_module_core.deprecation import deprecate, deprecated, deprecated_module


@deprecated(remove_in="0.1.0", use="new_fn()")
def old_fn(): ...  # warns on call; classes warn on instantiation


deprecated_module("pkg.old", remove_in="0.1.0", use="pkg.new")  # module scope of a shim module

_OLD_FORM = deprecate("old form of X", remove_in="0.1.0", use="new form")
_OLD_FORM.warn()  # in the code path kept for old callers
```

All three register in one registry. `host/tests/test_deprecation_expiry.py`
imports every shim and **fails once the installed `simple_module_core` version
reaches any registered `remove_in`**, so a shim cannot silently outlive its date:
that release either deletes it or moves the date on purpose. A new shim must be
added to that test's import list. Module-layout aliases are discovered automatically.
Non-Python fallbacks are registered explicitly by the test.

## Removed early (#989)

The shims previously scheduled for 0.1.0 have been removed. Old imports fail;
the pre-admin view URL redirects are gone. See the Unreleased **Removed** section
in [the changelog](https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md)
for every removed name and its replacement.

- Use framework settings registration/hydration and the settings module's area paths.
- Use `simple_module_hosting.permissions.RequiresPermission`: multiple keys have
  **any-of** semantics. `PermissionService.set_user_permissions` owns invalidation.
- Declare anonymous routes through `register_public_routes`; providers no longer
  contribute `get_public_paths`.
- Define `register_event_handlers(self, bus, app)` and pass `app` explicitly.
  Workers pass `None`; subscribe durable handlers before an `app is None` return.
- Use `optional()` for Inertia props, `ResourceType.share_roles` for share roles,
  and `simple_module_core.redirect_safety.safe_next` for safe redirects.

`ModuleMeta.requires_framework=None` permanently means **no version constraint**;
only its deprecation was removed. A declared range is still checked at boot.

`simple_module_hosting.settings.Settings`, `simple_module_hosting._registrations`,
`simple_module_core.public_routes`, `simple_module_core.versioning` and
`simple_module_core.resources` are live implementations, not import-path shims.
They remain; only their deprecated compatibility paths were removed.
