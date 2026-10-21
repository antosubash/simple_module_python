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
added to that test's import list. `simple_module_inertia` has no dependency on
core, so `props.lazy()` exposes `LAZY_REMOVE_IN` and the test registers it.

## Currently scheduled (remove in 0.1.0)

| Shim | Use instead |
|---|---|
| `host/routes_legacy.py` (301s from the pre-`/admin` view URLs) | the `/admin/*` URLs |
| `settings.registration`, `settings.module_registry`, `settings.hydrate` | `simple_module_core.module_settings`, `simple_module_core.settings_hydrate`, `simple_module_db.stored_settings` |
| `simple_module_inertia.props.lazy()` | `optional()` |
| one-argument `register_event_handlers(self, bus)` | `register_event_handlers(self, bus, app=None)` |
| `AuthProvider.get_public_paths()` (still honoured by `AuthMiddleware` and the maintenance gate) | `register_public_routes` |

`simple_module_hosting.settings.Settings` is **not** a shim: it is the combined
`HostSettings` + `BootstrapSettings` type used across the host.
