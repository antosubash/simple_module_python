# Module frontend tooling migration

Issues #958 and #959 move generated keys into their owners and Vite module
integration into a package. Upgrade all SimpleModule Python and npm packages
in lockstep. Existing apps can retain their copied Vite config until they adopt
the plugin; built-in `keys.<namespace>` imports remain available from
`@simple-module-py/i18n`.

## Adopt the Vite plugin

Add `@simple-module-py/vite-plugin` to the client's dev dependencies at the same
version as the other SimpleModule packages. Replace the copied module resolver,
asset aliases, dependency optimization, filesystem allowlist, React/Inertia dedupe
and generated-i18n plugin with:

```ts
import { simpleModule } from '@simple-module-py/vite-plugin';

// Inside defineConfig:
plugins: [...simpleModule({ root: import.meta.dirname }), react(), tailwindcss()],
```

Keep app-specific plugins, custom aliases, build inputs/output, base URL and
server settings. Remove imports of the old module-assets and vite.i18n helpers
when no longer used. Run `smpy gen` before building. Future asset resolver fixes
arrive through a package upgrade instead of edits to copied config files.

The plugin retains the previous installed-package digest fallback for apps that
have not generated an app-owned catalog yet. Once the app aggregate exists,
its digest controls dependency optimizer invalidation and dev-server restarts.

## Adopt portable keys

Module scaffolds now ship a generated local key file. In a module page use:

```ts
import { useT } from '@simple-module-py/i18n';
import { keys } from './i18n.generated';

// Inside the component:
const { t } = useT();
t(keys.orders.create.title);
```

Run `smpy gen` in a consuming app, or `smpy module verify` in the module repo,
after editing locales. Check the module-local generated file into source control
and include it in wheels alongside pages. Generation updates editable source
projects only; installed wheels and installed npm packages remain untouched.
Standalone scaffolding writes keys immediately, before any host exists.

Apps receive a generated i18n directory inside their client directory. Host-owned
pages can import `keys` from that aggregate; custom module pages use local keys.
Both extend `TranslationResources` from `@simple-module-py/i18n`, keeping `t()`
typed, including plural stems. The app aggregate also registers its key tree
through the generated page manifest, preserving older package-level custom key
imports without changing the app's copied Vite config. The framework repo also refreshes its central
compatibility files for existing built-in imports.

Older app namespaces remain available through package-level `keys` after
regenerating the page manifest and i18n files (in either order). New module code
should import local keys so it can ship independently. Previous modifications
under node_modules are no longer required or refreshed. This i18n migration does
not require adopting the Vite plugin.
