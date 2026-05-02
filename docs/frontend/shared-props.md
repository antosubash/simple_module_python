# Shared props & layout

Every Inertia response carries a set of shared props attached by `InertiaLayoutDataMiddleware`. They're available on every page without the server-side handler having to pass them.

## The contract

```ts
interface SharedProps {
  auth: {
    user: UserSummary | null;
    isAuthenticated: boolean;
    permissions: string[];
  };
  menus: {
    sidebar: MenuItem[];
    adminSidebar: MenuItem[];
    navbar: MenuItem[];
    userDropdown: MenuItem[];
  };
  i18n: {
    locale: string;
    bundle: Record<string, string>;
  };
  flash: { type: "success" | "error" | "info"; message: string } | null;
}
```

## How they're populated

`InertiaLayoutDataMiddleware` runs **last** in the middleware pipeline (closest to the app). For every outgoing Inertia response, it reads:

- `request.state.principal` (set by the users module's auth middleware) and the registered `principal_serializer` to build `auth.user`.
- `app.state.sm.menu_registry`, filtered by the current principal's permissions, to build `menus`.
- `request.state.locale` + `app.state.sm.i18n_registry` to build `i18n`.
- `request.session.pop("flash", None)` to build `flash`.

Then it merges those into the Inertia payload under the "shared" slot.

## Accessing from a page

### Typed helpers

Prefer the helpers from `@simple-module-py/ui`:

```tsx
import { useAuth, useMenus, useT } from "@simple-module-py/ui";

export default function Browse() {
  const { user, permissions } = useAuth();
  const { sidebar } = useMenus();
  const { t, locale } = useT();
  ...
}
```

### Raw

For cases where a helper doesn't cover your need, use Inertia's `usePage`:

```tsx
import { usePage } from "@inertiajs/react";
import type { SharedProps } from "@simple-module-py/ui";

const { props } = usePage<SharedProps>();
console.log(props.auth.user, props.i18n.locale);
```

## `auth.user` — the principal serializer

The framework doesn't know the shape of your `User`. A module (typically `users`) registers a `principal_serializer: Callable[[User], dict]` during `register_settings`:

```python
# modules/users/users/module.py
class UsersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.sm.inertia_config.register_principal_serializer(
            serialize_user
        )

def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": [r.name for r in user.roles],
    }
```

Without a registered serializer, `auth.user` is `None` even when a user is authenticated. This is intentional — the framework has no opinion on what a "user" is. If you replace the users module with your own auth, register your own serializer.

## Menus

Populated from the `MenuRegistry`. Each module adds items during `register_menu_items`:

```python
registry.add(MenuItem(
    section=MenuSection.SIDEBAR,
    key="orders",
    label_key="orders.menu.orders",
    href="/orders",
    icon="package",
    required_permission="orders.view",
    order=20,
))
```

`InertiaLayoutDataMiddleware` filters by `required_permission` before sending — users who lack it never see the item.

Render in a layout:

```tsx
import { useMenus } from "@simple-module-py/ui";

export function Sidebar() {
  const { sidebar } = useMenus();
  return (
    <nav>
      {sidebar.map((item) => (
        <a key={item.key} href={item.href}>
          {item.label}
        </a>
      ))}
    </nav>
  );
}
```

Labels are **pre-translated**. The middleware runs through `I18nRegistry` before serializing, so the client just renders `item.label`.

## `flash` — flash messages

Flash a message server-side with Starlette's session:

```python
@router.post("")
async def create(...):
    ...
    request.session["flash"] = {"type": "success", "message": "Order created"}
    return RedirectResponse("/orders", status_code=303)
```

`InertiaLayoutDataMiddleware` pops and forwards it. Consume in a toast component:

```tsx
import { useFlash } from "@simple-module-py/ui";
import { useEffect } from "react";
import { toast } from "sonner";

export function FlashToaster() {
  const flash = useFlash();
  useEffect(() => {
    if (flash) toast[flash.type](flash.message);
  }, [flash]);
  return null;
}
```

Shows once per request, then gone.

## `i18n` — the active bundle

`useT` reads the bundle and exposes `t(key, params?)`:

```tsx
const { t, locale } = useT();
t("orders.browse.title");
t("orders.items", { count: orders.length });   // pluralization
```

The bundle is the **resolved locale's** translations merged across all modules. Switching the locale (via `<LocaleSwitcher />` or a direct POST to `/i18n/set-locale`) triggers a full-page navigation so the bundle is re-fetched.

## Extending shared props

If your module needs to inject a new shared prop (e.g. feature flags), do **not** mutate `request.state.inertia_shared` from random handlers — wrap in a dedicated middleware:

```python
class FeatureFlagsSharedPropsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        flags = request.app.state.sm.feature_flags.evaluate_all(
            principal=getattr(request.state, "principal", None)
        )
        if not hasattr(request.state, "inertia_shared"):
            request.state.inertia_shared = {}
        request.state.inertia_shared["flags"] = flags
        return await call_next(request)
```

Register in `register_middleware`. Because it runs *before* `InertiaLayoutDataMiddleware` (framework middleware runs first on the way in), the flag dict is already attached when the framework middleware merges its own props.

On the client, extend the `SharedProps` type in your module's `contracts/` and re-export.
