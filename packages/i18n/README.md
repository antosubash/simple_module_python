# @simple-module-py/i18n

`i18next` + `react-i18next` glue for [simple_module](https://github.com/antosubash/simple_module_python) apps. Ships an `i18next` instance pre-configured for the framework's per-module locale conventions (`<module>.<key>` namespacing, CLDR plurals, cookie-driven locale switching).

## Install

```bash
npm install @simple-module-py/i18n
```

Peer-depends on React 19. Runtime deps `i18next` and `react-i18next` install automatically.

## What it provides

- `createI18n({ locale, resources })` — returns a configured `i18next` instance.
- `<I18nProvider>` — React context provider; plug it at the root of your Inertia app.
- `useT(namespace?)` — hook returning the translation function, scoped if you pass a namespace.
- `withNamespace(ns)` — higher-order helper for components that want a stable namespace binding.

## Usage

Root setup (in `client_app/main.tsx`):

```tsx
import { createI18n, I18nProvider } from "@simple-module-py/i18n";

const i18n = createI18n({
  locale: window.__INITIAL_LOCALE__ ?? "en",
  resources: window.__I18N_RESOURCES__, // provided by InertiaLayoutDataMiddleware
});

function Root({ App, props }) {
  return (
    <I18nProvider i18n={i18n}>
      <App {...props} />
    </I18nProvider>
  );
}
```

In a module page:

```tsx
import { useT } from "@simple-module-py/i18n";

export default function Browse() {
  const t = useT("orders");
  return <h1>{t("browse.title")}</h1>;  // resolves to orders.browse.title
}
```

**Important:** when using `zod` schemas with translated messages, build the schema *inside* a component that calls `useT()` — never at module scope. Schemas constructed at import time freeze against the first render's locale.

## Depends on

- `i18next`, `react-i18next`
- Peer: `react ^19.0.0`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
