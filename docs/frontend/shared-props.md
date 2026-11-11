# Shared props & layout

Every Inertia response carries a set of shared props attached by `InertiaLayoutDataMiddleware`. They're available on every page without the server-side handler having to pass them.

## The contract

```ts
// The exported SharedProps type (packages/ui/src/types.ts) covers auth + menus + i18n, plus
// the optional signup, homeUrl, demo and branding props:
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
interface I18nSharedProps {   // SharedProps['i18n']
  locale: string;
  audience: 'public' | 'full';
  supportedLocales: string[];
  messages: Record<string, string> | null;   // null when the tab reports the same locale and audience
}
```

## How they're populated

`InertiaLayoutDataMiddleware` resolves permissions eagerly and installs a memoised
async layout factory. Page dependencies and error rendering resolve that factory;
JSON API requests and downloads skip it. The resolved props remain available as
`request.state.inertia_shared`; custom readers first await
`resolve_inertia_shared(request)` from `simple_module_hosting.inertia_deps`.
For each rendered page, it reads:

- `request.state.user` (set by the auth middleware) and the registered `app.state.principal_serializer` to build `auth.user`. The user's roles drive `auth.permissions`.
- `menu_registry.get_for_user(...)`, filtered by the user's auth state and roles, to build `menus`.
- `request.state.locale` + `app.state.sm.i18n_registry` to build `i18n`.

Then it stores the result on `request.state.inertia_shared`, which `get_inertia` (`simple_module_hosting.inertia_deps`) shares into the Inertia payload.

## Accessing from a page

`@simple-module-py/ui` registers `SharedProps` with Inertia (`InertiaConfig.sharedPageProps`), so `usePage().props` is already typed: no generic, no cast. A page gets its own props as typed component arguments; a component or layout that needs the page's own props as well uses `usePageProps<T>()`, which returns `T & SharedProps & { errors }`. Use `useT` from `@simple-module-py/i18n` for translations:

```tsx
import { useT } from "@simple-module-py/i18n";
import { usePageProps } from "@simple-module-py/ui";

interface Props {
  orders: Order[];
}

// A page: own props as arguments, shared ones from usePageProps.
export default function Browse({ orders }: Props) {
  const { auth, menus } = usePageProps();
  const { t } = useT();
  // auth.user, auth.permissions, menus.sidebar, ...
}

// A component that cannot receive props as arguments:
function OrderCount() {
  const { orders } = usePageProps<Props>();
  return <span>{orders.length}</span>;
}
```

Do not write `usePage<{ props: X }>().props as unknown as X`. The `usePage` generic is the props type itself, not `{ props: X }`, so that form was already wrong, and the cast hid it. `make lint` (`scripts/check_no_double_cast.py`) rejects `as unknown as` in pages, components, `packages/ui` and `host/client_app` unless the line (or the one above) carries `// cast-ok: <reason>`.

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
registry.add(
    MenuItem(
        section=MenuSection.SIDEBAR,
        label="Orders",
        url="/orders",
        icon="package",
        requires_auth=True,
        roles=["admin"],  # empty list = visible to all authenticated users
        order=20,
    )
)
```

`menu_registry.get_for_user(is_authenticated=..., roles=...)` filters by `requires_auth` and `roles` before sending — users without a matching role never see the item.

Render in a layout via `usePageProps`:

```tsx
import type { MenuItem } from "@simple-module-py/ui";
import { usePageProps } from "@simple-module-py/ui";

export function Sidebar() {
  const { menus } = usePageProps();
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

Each tab advertises its cached locale/audience via `X-SM-I18n`. A matching
Inertia visit receives `messages: null`; otherwise the server resends the catalog.
The client reloads `i18n` once if it receives a changed locale without messages.
The client side is `bootI18nFromInitialPage` and `subscribeI18nToNavigation(router)` from
`@simple-module-py/i18n/inertia`; call both in `createInertiaApp`'s `setup()` (this repo's host
and `smpy new` apps do).

The `i18n.messages` block is the **resolved locale's** translations merged across all modules. Switching the locale (via `<LocaleSwitcher />`, which POSTs to `/i18n/set-locale`) triggers a full-page navigation so the messages are re-fetched. The active locale and supported locales are on `usePage().props.i18n` (`locale`, `supportedLocales`).

## Extending shared props

Register a sync or async provider with
`simple_module_hosting.register_inertia_shared_provider(app, provider)` from a
module lifecycle hook. It runs once when shared props are resolved, and its
returned dict is merged after the built-in props. Reserved keys cannot be
overwritten; provider failures are logged and skipped.

On the client, a module-specific shared prop is read with `usePageProps<{ flags: Flags }>()`; props every app needs belong in `SharedProps` (`packages/ui/src/types.ts`).
