# Shared props & layout

Every Inertia response carries a set of shared props attached by `InertiaLayoutDataMiddleware`. They're available on every page without the server-side handler having to pass them.

## The contract

```ts
// The exported SharedProps type (packages/ui/src/types.ts) covers auth + menus:
interface SharedProps {
  auth: {
    user: { name: string; email: string; roles: string[] } | null;
    isAuthenticated: boolean;
    permissions: string[];
  };
  menus: {
    sidebar: MenuItem[];
    adminSidebar: MenuItem[];
    navbar: MenuItem[];
    userDropdown: MenuItem[];
  };
}

// Every Inertia response also carries an `i18n` block (read via usePage().props.i18n):
interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  messages: Record<string, string> | null;   // null on Inertia XHR partials when the locale is unchanged
}
```

## How they're populated

`InertiaLayoutDataMiddleware` runs **last** in the middleware pipeline (closest to the app). For every outgoing Inertia response, it reads:

- `request.state.user` (set by the auth middleware) and the registered `app.state.principal_serializer` to build `auth.user`. The user's roles drive `auth.permissions`.
- `menu_registry.get_for_user(...)`, filtered by the user's auth state and roles, to build `menus`.
- `request.state.locale` + `app.state.sm.i18n_registry` to build `i18n`.

Then it stores the result on `request.state.inertia_shared`, which `get_inertia` (`simple_module_hosting.inertia_deps`) shares into the Inertia payload.

## Accessing from a page

Read `auth` / `menus` via Inertia's `usePage` and the exported `SharedProps` type; use `useT` from `@simple-module-py/i18n` for translations:

```tsx
import { usePage } from "@inertiajs/react";
import { useT } from "@simple-module-py/i18n";
import type { SharedProps } from "@simple-module-py/ui";

export default function Browse() {
  const { auth, menus } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const { t } = useT();
  // auth.user, auth.permissions, menus.sidebar, ...
}
```

The layouts in `@simple-module-py/ui` (`SidebarLayout`, `PublicLayout`, …) read these props for you, so most pages don't touch `usePage` directly.

## `auth.user` — the principal serializer

The framework doesn't know the shape of your `User`. A module (the `auth` module) assigns a serializer to `app.state.principal_serializer` during `register_settings`:

```python
# modules/auth/auth/module.py
def _serialize_principal(user: UserContext) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
    }

class AuthModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.auth = AuthState()
        app.state.principal_serializer = _serialize_principal
```

Without a registered serializer, `auth.user` is `None` even when a user is authenticated. This is intentional — the framework has no opinion on what a "user" is. If you replace the auth module with your own, register your own serializer on `app.state.principal_serializer`.

## Menus

Populated from the `MenuRegistry`. Each module adds items during `register_menu_items`:

```python
registry.add(MenuItem(
    section=MenuSection.SIDEBAR,
    label="Orders",
    url="/orders",
    icon="package",
    requires_auth=True,
    roles=["admin"],   # empty list = visible to all authenticated users
    order=20,
))
```

`menu_registry.get_for_user(is_authenticated=..., roles=...)` filters by `requires_auth` and `roles` before sending — users without a matching role never see the item.

Render in a layout via `usePage` and the `SharedProps` type:

```tsx
import { usePage } from "@inertiajs/react";
import type { MenuItem, SharedProps } from "@simple-module-py/ui";

export function Sidebar() {
  const { menus } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  return (
    <nav>
      {menus.sidebar.map((item: MenuItem) => (
        <a key={item.url} href={item.url}>
          {item.label}
        </a>
      ))}
    </nav>
  );
}
```

Labels are passed through as `item.label` — the module supplies the display string when it registers the item.

## Toasts

There is no `flash` shared prop. Pages fire toasts directly from their own request callbacks using `sonner`:

```tsx
import { toast } from "sonner";

router.post("/api/orders", data, {
  onSuccess: () => toast.success("Order created"),
  onError: () => toast.error("Failed to create order"),
});
```

For server-driven error messages, the Inertia config enables fastapi-inertia's `use_flash_errors`, which surfaces validation errors on the page's `errors` prop.

## `i18n` — the active messages

`useT` (from `@simple-module-py/i18n`, a re-export of react-i18next's `useTranslation`) exposes `t(key, params?)`:

```tsx
import { useT } from "@simple-module-py/i18n";

const { t } = useT();
t("orders.browse.title");
t("orders.items", { count: orders.length });   // pluralization
```

The `i18n.messages` block is the **resolved locale's** translations merged across all modules. Switching the locale (via `<LocaleSwitcher />`, which POSTs to `/i18n/set-locale`) triggers a full-page navigation so the messages are re-fetched. The active locale and supported locales are on `usePage().props.i18n` (`locale`, `supportedLocales`).

## Extending shared props

If your module needs to inject a new shared prop (e.g. feature flags), do **not** mutate `request.state.inertia_shared` from random handlers — wrap in a dedicated middleware:

```python
class FeatureFlagsSharedPropsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        flags = request.app.state.sm.feature_flags.evaluate_all(
            principal=getattr(request.state, "user", None)
        )
        if not hasattr(request.state, "inertia_shared"):
            request.state.inertia_shared = {}
        request.state.inertia_shared["flags"] = flags
        return await call_next(request)
```

Register in `register_middleware`. Because it runs *before* `InertiaLayoutDataMiddleware` (framework middleware runs first on the way in), the flag dict is already attached when the framework middleware merges its own props.

On the client, extend the `SharedProps` type in your module's `contracts/` and re-export.
