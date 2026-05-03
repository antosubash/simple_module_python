# Pages & discovery

Every `.tsx` file under `modules/<name>/<name>/pages/` is an Inertia page, automatically discovered by `make gen-pages` and resolvable from server-side `inertia.render(...)` calls.

## Page keys

The server identifies a page by a **key**: `"<ModuleName>/<PageName>"`.

| File | Page key |
|---|---|
| `modules/orders/orders/pages/Browse.tsx` | `"Orders/Browse"` |
| `modules/orders/orders/pages/Create.tsx` | `"Orders/Create"` |
| `modules/orders/orders/pages/admin/Settings.tsx` | `"Orders/admin/Settings"` |
| `modules/blog_posts/blog_posts/pages/Edit.tsx` | `"BlogPosts/Edit"` |
| `client_app/pages/Landing.tsx` | `"Landing"` (host-level, no namespace) |

- **`<ModuleName>`** is the **PascalCase** of the module's package directory: `blog_posts` → `BlogPosts`, `file_storage` → `FileStorage`.
- **`<PageName>`** is the path under `pages/` minus `.tsx`. Subdirectories become slashes: `admin/Settings.tsx` → `admin/Settings`.
- **Host-level pages** live under `client_app/pages/` and use just the page name without a namespace prefix.

## Rendering

```python
# In an endpoint
return await inertia.render(
    "Orders/Browse",
    props={"orders": [...]},
)
```

The key must match a generated entry in `modules.generated.ts`. Mismatches produce:

- **`SM003`** (warning) — the `.tsx` file exists, but no `inertia.render()` call in any module references it. The page is orphaned.
- **`SM004`** (warning) — an `inertia.render("Orders/Unknown", ...)` call exists, but there's no matching `.tsx` file. You'll get a runtime error when a user hits that route.

Both fire at app boot.

## The generation pipeline

`make gen-pages` (invoked automatically by `make dev` before starting Vite) runs `scripts/gen_pages.py`. It:

1. Discovers every installed module's page directory.
2. Builds an object literal mapping page keys to dynamic imports.
3. Writes three files to `client_app/`:
   - `modules.generated.ts` — the `resolvePage` function used by Inertia.
   - `modules.manifest.json` — metadata used by diagnostics.
   - `modules.generated.css` — imports for any module-scoped CSS.

These files are **regenerated on every `make dev` run**. Never hand-edit them. Add them to `.gitignore` if they aren't already.

```ts
// client_app/modules.generated.ts  (generated)
export async function resolvePage(name: string) {
  switch (name) {
    case "Orders/Browse":
      return (await import("../../modules/orders/orders/pages/Browse.tsx")).default;
    case "Orders/Create":
      return (await import("../../modules/orders/orders/pages/Create.tsx")).default;
    // ...
    default:
      throw new Error(`Unknown page: ${name}`);
  }
}
```

Vite resolves these imports normally at build time and HMR-watches them in dev.

## Writing a page

A minimal page:

```tsx
// modules/orders/orders/pages/Browse.tsx
import { useT } from "@simple-module-py/i18n-react";
import { PageHeader } from "@simple-module-py/ui";
import type { OrderOut } from "../contracts";

interface BrowseProps {
  orders: OrderOut[];
}

export default function Browse({ orders }: BrowseProps) {
  const { t } = useT();
  return (
    <>
      <PageHeader title={t("orders.browse.title")} />
      <ul>
        {orders.map((o) => (
          <li key={o.id}>
            {o.customer_email} — {o.status}
          </li>
        ))}
      </ul>
    </>
  );
}
```

- `export default` is **required** — Inertia's resolver expects a default export.
- Props are passed from the server; type them explicitly.
- Use `useT()` for i18n and `useAuth()` / `useMenus()` from `@simple-module-py/ui` for shared props.

## Subdirectories

Organize larger modules into subdirectories. The page key uses forward slashes:

```
modules/orders/orders/pages/
├── Browse.tsx
├── admin/
│   ├── Dashboard.tsx      → "Orders/admin/Dashboard"
│   └── Settings.tsx       → "Orders/admin/Settings"
└── customer/
    └── Portal.tsx         → "Orders/customer/Portal"
```

## Layouts

Shared layouts live in `packages/ui/src/layouts/`. Use them via JSX composition:

```tsx
import { AuthenticatedLayout } from "@simple-module-py/ui";

export default function Browse({ orders }) {
  return (
    <AuthenticatedLayout>
      <PageHeader title="Orders" />
      ...
    </AuthenticatedLayout>
  );
}
```

Or use Inertia's persistent-layout pattern for layouts that survive navigation:

```tsx
Browse.layout = (page: ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
```

The second form re-uses the layout instance across navigations — good for layouts with expensive setup or local state you want preserved.

## Shared components

`packages/ui` is a shared shadcn-based component library. It's a proper npm workspace — import via its package name, not relative paths:

```tsx
// ✅
import { Button, DataTable, Input } from "@simple-module-py/ui";

// ❌
import { Button } from "../../../../packages/ui/src/components/ui/Button";
```

The Vite alias is set up so `@simple-module-py/ui` resolves at build time.

## Module-scoped CSS

If your module needs its own CSS (beyond Tailwind classes), put it in `modules/<name>/<name>/pages/<name>.css` and import it from the page:

```tsx
import "./Browse.css";
```

`make gen-pages` also emits `modules.generated.css`, which imports any `<module>/styles.css` declared at the module level.

## Page-level TypeScript

Each module's `tsconfig.json` extends the host's; page files can import across module boundaries (from `<other_module>/contracts`) freely. Cross-module imports from anything *other than* `contracts` is a code smell — you're reaching into implementation details.

## Testing pages

React tests use Vitest + Testing Library, configured in `vitest.setup.ts`. A minimal page test:

```tsx
// modules/orders/orders/pages/__tests__/Browse.test.tsx
import { render, screen } from "@testing-library/react";
import Browse from "../Browse";

it("renders orders", () => {
  render(<Browse orders={[{ id: 1, customer_email: "a@b.c", status: "pending" }]} />);
  expect(screen.getByText(/a@b.c/)).toBeInTheDocument();
});
```

For tests that hit shared props (`useT`, `useAuth`), wrap in a mock provider — see `packages/ui/src/test-utils.tsx`.
