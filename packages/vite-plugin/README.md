# @simple-module-py/vite-plugin

Vite integration for SimpleModule hosts. Versioned in lockstep with the Python
framework and the other `@simple-module-py` packages. Requires Vite 8.

## Install

Install `@simple-module-py/vite-plugin` at the same version as the framework.

## Usage

```ts
import { simpleModule } from '@simple-module-py/vite-plugin';
import { defineConfig } from 'vite';

export default defineConfig({
  root: import.meta.dirname,
  plugins: [...simpleModule({ root: import.meta.dirname })],
});
```

Keep React, Tailwind, build output and dev-server settings in the app's config.
Run `smpy gen` before Vite. The plugin reads the generated module manifests to
configure filesystem access, cross-module aliases, hoisted bare-import resolution,
React/Inertia deduplication and dependency optimization. Its dev-only i18n plugin
hashes the app-owned generated catalog (or the installed package's compatibility
files for older apps) and restarts Vite when it changes.

Existing copied configs continue working. To adopt this package, replace their
module asset/resolver/optimizer/i18n blocks with `simpleModule({ root })` and
retain app-specific plugins and options. Future resolver fixes require a package
upgrade instead of edits to copied helper files.

The published package contains JavaScript and type declarations. `npm install`
builds workspace sources through the prepare hook; `npm run build` rebuilds them
after editing the plugin.
