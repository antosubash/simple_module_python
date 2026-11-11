# @simple-module-py/i18n

`i18next` + `react-i18next` glue for [simple_module](https://github.com/antosubash/simple_module_python) apps. Ships an `i18next` instance pre-configured for the framework's per-module locale conventions (`<module>.<key>` namespacing, CLDR plurals, cookie-driven locale switching).

## Install

```bash
npm install @simple-module-py/i18n
```

Peer-depends on React 19. Runtime deps `i18next` and `react-i18next` install automatically.

## What it provides

- `configureI18n({ locale, messages })` — initialise the shared `i18next` instance once at boot with the active-locale messages.
- `updateI18n({ locale, messages })` — call when an Inertia visit brings a new locale (adds the resource bundle, switches language).
- `useT()` — re-exported `react-i18next` `useTranslation` hook; returns `{ t }`.
- `t` — non-hook translation accessor (re-exported from `i18next`) for use in schemas or utilities.
- `keys` — generated, typed key tree (`keys.<module>.<...>`) you pass to `t()`.
- `@simple-module-py/i18n/inertia` — `bootI18nFromInitialPage(i18n)` and `subscribeI18nToNavigation(router)`: keep each tab's catalog in step with the server. Every Inertia visit reports the catalog the tab holds in `X-SM-I18n`, adopts the catalog the server sends back, and reloads `i18n` once when the locale changed without one.

## Usage

Root setup (in `client_app`):

```tsx
import { router } from "@inertiajs/react";
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from "@simple-module-py/i18n/inertia";

// In createInertiaApp's setup(), from the initial page's shared props:
bootI18nFromInitialPage(props.initialPage.props.i18n);
subscribeI18nToNavigation(router);
```

`configureI18n` / `updateI18n` remain for an app that wires navigation itself.

In a module page:

```tsx
import { keys, useT } from "@simple-module-py/i18n";

export default function Browse() {
  const { t } = useT();
  return <h1>{t(keys.orders.browse.title)}</h1>;  // resolves to orders.browse.title
}
```

**Important:** when using `zod` schemas with translated messages, build the schema *inside* a component that calls `useT()` — never at module scope. Schemas constructed at import time freeze against the first render's locale.

## Depends on

- `i18next`, `react-i18next`
- Peer: `react ^19.0.0`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
