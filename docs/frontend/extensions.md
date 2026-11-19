# Frontend extension points

Modules can add panels to existing pages, replace layout chrome, add menu icons,
and supply settings controls through one frontend registry. Without registrations,
the existing pages, chrome, icons and controls behave as before.

## Registration and startup

Ship one optional frontend entry at `<package>/ui/extensions.ts` (or `.tsx`),
exporting a synchronous named `register(registry)` function. Run `smpy gen` after
adding or removing an entry. Discovery uses the same installed, selected modules
as page generation, including modules without pages. The generator rejects a
package shipping both entry extensions rather than choosing one silently.

Generated imports preserve module dependency order. Entries are small, eager
registration functions; expensive components belong in lazy imports. Registration
runs once per registry before the first React render, never on page navigation.
Duplicate slot ids or icon names throw. Layout components and settings renderers
use the last registration, so a dependent module can replace a dependency's choice.

New scaffolded hosts already initialize extensions. In an existing host, import
`registerModuleExtensions` from `./modules.generated` and add this before
`createInertiaApp`:

```tsx
import { extensions, ExtensionsProvider } from '@simple-module-py/ui/extensions';
import { LayoutComponentsProvider } from '@simple-module-py/ui/layouts/LayoutComponentsProvider';
import { registerModuleExtensions } from './modules.generated';

registerModuleExtensions(extensions);
// Optional host registrations run here, after module registrations.
// registerHostExtensions(extensions);
```

Wrap the Inertia `<App {...props} />` in `ExtensionsProvider`, then
`LayoutComponentsProvider`. Register everything before rendering. Registrations
are startup configuration, not reactive state; after changing an entry during
development, reload the document. For an isolated app or tests, construct an
`ExtensionRegistry`, register into it, and pass it as the provider's `registry`.

## Ordered page slots

```tsx
import { lazy } from 'react';
import { type ExtensionRegistry, slots } from '@simple-module-py/ui/extensions';
import { Skeleton } from '@simple-module-py/ui/components/ui/skeleton';

const AccessPanel = lazy(() => import('./components/AccessPanel'));

export function register(registry: ExtensionRegistry) {
  registry.registerSlot(slots.usersEditPanels, {
    id: 'my_module.access',
    order: 20,
    permission: 'my_module.access.read',
    component: AccessPanel,
    fallback: <Skeleton className="h-48" />,
  });
}
```

The component receives the slot's typed props:

| Constant | Slot name | Props | Placement |
| --- | --- | --- | --- |
| `slots.usersEditPanels` | `users.edit.panels` | `{ userId: string }` | Users edit card grid, before the danger zone |
| `slots.tenantsSettingsSections` | `tenants.settings.sections` | `{ tenant: { id, name, slug } }` (all strings) | After the active tenant's settings |

Lower `order` values render first; omitted order is zero. Ties preserve
registration order. An empty slot adds no markup. Contributions own their card or
section container. An optional `fallback` reserves the panel's space while its
lazy component loads; match its dimensions to the loaded panel. Additional host
pages can render `<Slot name={...} props={...} />`
and declare their props by augmenting the exported `ExtensionSlots` interface.

The optional `permission` is checked against the current page's shared
`auth.permissions` on every render. Missing permissions deny the contribution
before its lazy component loads. This only controls visibility: endpoints must
still enforce authorization, and tenant routes must use the active tenant.

## Layout chrome and icons

The app-level `LayoutComponentsProvider` supplies `UserMenu` and `Topbar`, used by
both authenticated and admin sidebar layouts. Their defaults are
`SidebarUserMenu` and `AppTopbar`. Replacement components receive the same typed
props, including navigation callbacks for the user menu and current navigation
context for the topbar. Exported `LayoutComponents` describes these contracts.

```tsx
export function register(registry: ExtensionRegistry) {
  registry.registerLayout('UserMenu', MyUserMenu);
  registry.registerLayout('Topbar', MyTopbar);
  registry.registerIcon('my_module.orbit', OrbitIcon);
}
```

Custom icons receive `className`, `aria-hidden` and `strokeWidth`. Use the
registered name as the backend menu item's `icon`. Icons are additive: built-in
names retain their original glyphs even if a registration uses the same name.
Prefer a module prefix to avoid collisions. Unknown names render the existing
empty span and log a warning in development. A lazy icon reserves that same box
while loading.

## Settings field controls

Declare a control hint on a DB-backed settings field:

```python
from pydantic import Field

from simple_module_core.settings_base import DbBackedSettings


class MySettings(DbBackedSettings):
    starts_on: str = Field(default="", json_schema_extra={"control": "my_module.date"})
```

The settings API and Inertia props include `control` in the field metadata. The
hint changes the editor only; normal server validation and storage still apply.
Register its renderer through the same frontend entry:

```tsx
import type { SettingsFieldRendererProps } from '@simple-module-py/ui/extensions';

function DateInput({ field, value, onChange, id }: SettingsFieldRendererProps) {
  return (
    <input
      id={id}
      type="date"
      value={String(value ?? '')}
      onChange={(event) => onChange(field.name, event.target.value)}
    />
  );
}

export function register(registry: ExtensionRegistry) {
  registry.registerFieldRenderer('my_module.date', DateInput);
}
```

Renderers receive the whole field metadata, the current draft value, the label's
input `id`, and `onChange(name, value)`. Preserve nullable semantics, choices,
override highlighting and accessible labels as appropriate for the control.
Secret fields keep the existing masked input until the user chooses to set a
new value; then a custom renderer can edit that new draft. Missing or unknown
control hints use the built-in controls.

## Bundle size and loading

Use direct imports from `@simple-module-py/ui/extensions` in registration entries
to keep unrelated UI out of their dependency graph. Use `React.lazy` for panels,
field renderers or custom icons that bring in heavy libraries. Hidden slot
contributions do not load their chunks. Slots and custom field controls have
local Suspense boundaries; lazy chrome should supply its own boundary and
placeholder. For a lazy settings renderer, register a small wrapper that supplies
its own Suspense boundary with a control-sized placeholder. Put a stable skeleton
inside your contribution when its data needs to load, and translate all
user-visible copy with `t(keys...)`.

See [Fast pages](./performance.md) for loading and layout-shift guidance. No demo
module is needed to enable extensions; the registry remains empty by default.
