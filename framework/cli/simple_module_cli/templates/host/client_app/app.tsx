import { createInertiaApp, router } from '@inertiajs/react';
import { configureI18n, updateI18n } from '@simple-module-py/i18n';
import { formatTitle, setTitleAppName } from '@simple-module-py/ui/lib/app-title';
import { resolveServerHead } from '@simple-module-py/ui/lib/server-head';
import { startSpaLinkInterception } from '@simple-module-py/ui/lib/spa-links';
import { initTheme } from '@simple-module-py/ui/lib/theme';
import { createRoot } from 'react-dom/client';
import { resolvePage } from './pages';

type I18nBlock = {
  locale: string;
  supportedLocales?: string[];
  messages: Record<string, string> | null;
};

createInertiaApp({
  title: (title) => formatTitle(title),
  // Re-emits the `_head` prop (server-rendered SEO tags) on client visits.
  serverHead: resolveServerHead,
  resolve: async (name) => {
    return await resolvePage(name);
  },
  setup({ el, App, props }) {
    const pageProps = props.initialPage.props as {
      i18n?: I18nBlock;
      branding?: { appName?: string | null };
    };
    setTitleAppName(pageProps.branding?.appName);
    // Before the first render, so a dark-theme user never sees a light frame.
    initTheme();
    const initial = pageProps.i18n;
    configureI18n({
      locale: initial?.locale ?? 'en',
      messages: initial?.messages ?? {},
    });
    router.on('success', (event) => {
      const block = (event.detail.page.props as { i18n?: I18nBlock }).i18n;
      // A non-null `messages` payload IS the server's signal that the client
      // needs it — the backend sends `null` whenever the catalog the client
      // already holds is still good. Gating on a locale change instead drops
      // the catalog that arrives when the *audience* changes: signing in swaps
      // the anonymous snapshot for one including admin-only modules, at the
      // same locale, so every admin screen rendered raw keys
      // ("dashboard.home.title") until a hard refresh.
      if (block?.messages) {
        updateI18n({ locale: block.locale, messages: block.messages });
      }
    });
    // Authored content (pagebuilder widgets, markdown and rich-text fields)
    // renders author-entered URLs as plain <a href>, which the browser would
    // follow with a full document load. This app is client-rendered, so that
    // means a blank page until the bundle boots. Route them through Inertia.
    startSpaLinkInterception();
    createRoot(el).render(<App {...props} />);
  },
  progress: {
    color: '#4B5563',
    delay: 150,
  },
});
