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
| `host/client_app/pages/Landing.tsx` | `"Landing"` (host-level, no namespace) |

- **`<ModuleName>`** is the module's `ModuleMeta.name` — by convention the **PascalCase** of the module's package directory: `blog_posts` → `BlogPosts`, `file_storage` → `FileStorage`.
- **`<PageName>`** is the path under `pages/` minus `.tsx`. Subdirectories become slashes: `admin/Settings.tsx` → `admin/Settings`.
- **Host-level pages** live under `host/client_app/pages/` and use just the page name without a namespace prefix.

## Rendering

```python
# In an endpoint
return await inertia.render(
    "Orders/Browse",
    props={"orders": [...]},
)
```

The key must resolve against the page map built from `modules.generated.ts`. Mismatches produce:

- **`SM003`** (warning) — the `.tsx` file exists, but no `inertia.render()` call in any module references it. The page is orphaned.
- **`SM004`** (warning) — an `inertia.render("Orders/Unknown", ...)` call exists, but there's no matching `.tsx` file. You'll get a runtime error when a user hits that route.

Both fire at app boot.

## The generation pipeline

`make gen-pages` (invoked automatically by `make dev` before starting Vite) runs `smpy host gen-pages --host-dir=host/client_app` (`simple_module_hosting.manifest.write_module_pages_manifest`). It:

1. Discovers every installed module's page directory.
2. Emits one `import.meta.glob` call per module, keyed by the module's `meta.name`.
3. Writes three files to `host/client_app/`:
   - `modules.generated.ts` — exports `moduleGlobs` (a `Record<ModuleName, Record<filePath, loader>>`).
   - `modules.manifest.json` — name → absolute pages dir, used by Vite and diagnostics.
   - `modules.generated.css` — `@source` entries for wheel-installed module pages.

These files are **regenerated on every `make dev` run** (only rewritten when content changes) and are **gitignored**. Never hand-edit them.

```ts
// host/client_app/modules.generated.ts  (generated)
export const moduleGlobs: Record<string, Record<string, () => Promise<PageModule>>> = {
  "Orders": import.meta.glob<PageModule>("../../modules/orders/orders/pages/**/*.tsx"),
  // ...
};
```

`host/client_app/pages.ts` (hand-written) turns `moduleGlobs` plus the host's own `./pages/**/*.tsx` glob into a `{ "<ModuleName>/<PageName>": loader }` map and exports the `resolvePage(name)` used by Inertia. Vite resolves these imports normally at build time and HMR-watches them in dev.

## Writing a page

A minimal page:

```tsx
// modules/orders/orders/pages/Browse.tsx
import { useT } from "@simple-module-py/i18n";
import { SectionTitle } from "@simple-module-py/ui/components/SectionTitle";
import type { OrderOut } from "../contracts";

interface BrowseProps {
  orders: OrderOut[];
}

export default function Browse({ orders }: BrowseProps) {
  const { t } = useT();
  return (
    <>
      <SectionTitle>{t("orders.browse.title")}</SectionTitle>
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
- Use `useT()` from `@simple-module-py/i18n` for translations and `usePage()` (with the `SharedProps` type from `@simple-module-py/ui`) for `auth` / `menus`.

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

`packages/ui` is a shared shadcn-based component library. It's a proper npm workspace — import via its package name, not relative paths. Module pages import shadcn primitives and layouts from their subpaths:

```tsx
// ✅
import { Button } from "@simple-module-py/ui/components/ui/button";
import { StatCard } from "@simple-module-py/ui/components/StatCard";
import { AuthenticatedLayout } from "@simple-module-py/ui/layouts/AuthenticatedLayout";

// ❌
import { Button } from "../../../../packages/ui/src/components/ui/button";
```

The package's `exports` map and tsconfig `paths` resolve `@simple-module-py/ui/*` at build time.

## Module-scoped CSS

If your module needs its own CSS (beyond Tailwind classes), put it in `modules/<name>/<name>/pages/<name>.css` and import it from the page:

```tsx
import "./Browse.css";
```

`make gen-pages` also emits `modules.generated.css` with Tailwind `@source` entries for wheel-installed module pages (in-repo modules are already covered by the static `@source` glob in `host/client_app/styles.css`).

## Page-level TypeScript

Each module's `tsconfig.json` extends the host's; page files can import across module boundaries (from `<other_module>/contracts`) freely. Cross-module imports from anything *other than* `contracts` is a code smell — you're reaching into implementation details.

## Testing pages

React tests use Vitest + Testing Library, configured in the repo-root `vitest.config.ts` + `vitest.setup.ts` and run via `npm test`. A minimal page test:

```tsx
// packages/ui/src/components/StatCard.test.tsx
import { render, screen } from "@testing-library/react";
import Browse from "./Browse";

it("renders orders", () => {
  render(<Browse orders={[{ id: 1, customer_email: "a@b.c", status: "pending" }]} />);
  expect(screen.getByText(/a@b.c/)).toBeInTheDocument();
});
```

The root `vitest.config.ts` only includes tests under `packages/**` and `host/client_app/**`, so place `.test.tsx` files there. For components that read shared props (`useT`, `usePage`), mock the source module with `vi.mock("@simple-module-py/i18n", ...)` / `vi.mock("@inertiajs/react", ...)` — see `packages/ui/src/components/LocaleSwitcher.test.tsx`.
