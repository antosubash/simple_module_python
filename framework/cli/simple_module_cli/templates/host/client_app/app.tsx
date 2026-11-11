import { createInertiaApp, router } from '@inertiajs/react';
import {
  bootI18nFromInitialPage,
  type I18nPageBlock,
  subscribeI18nToNavigation,
} from '@simple-module-py/i18n/inertia';
import { formatTitle, setTitleAppName } from '@simple-module-py/ui/lib/app-title';
import { resolveServerHead } from '@simple-module-py/ui/lib/server-head';
import {
  isExcluded,
  readNativePrefixes,
  startSpaLinkInterception,
} from '@simple-module-py/ui/lib/spa-links';
import { initTheme } from '@simple-module-py/ui/lib/theme';
import { createRoot } from 'react-dom/client';
import { resolvePage } from './pages';

createInertiaApp({
  title: (title) => formatTitle(title),
  // Re-emits the `_head` prop (server-rendered SEO tags) on client visits.
  serverHead: resolveServerHead,
  resolve: async (name) => {
    return await resolvePage(name);
  },
  setup({ el, App, props }) {
    const pageProps = props.initialPage.props as {
      i18n?: I18nPageBlock;
      branding?: { appName?: string | null };
    };
    setTitleAppName(pageProps.branding?.appName);
    // Before the first render, so a dark-theme user never sees a light frame.
    initTheme();
    // Reports this tab's catalog in `X-SM-I18n` on every visit and adopts the
    // catalog the server sends back, so each tab keeps its own (#788, #871).
    bootI18nFromInitialPage(pageProps.i18n);
    subscribeI18nToNavigation(router);
    // Authored content (pagebuilder widgets, markdown and rich-text fields)
    // renders author-entered URLs as plain <a href>, which the browser would
    // follow with a full document load. This app is client-rendered, so that
    // means a blank page until the bundle boots. Route them through Inertia.
    // Legacy SPA mounts and `native_link_prefixes` stay full navigations.
    let nativePrefixes = readNativePrefixes(props.initialPage.props);
    router.on('navigate', (event) => {
      nativePrefixes = readNativePrefixes(event.detail.page.props);
    });
    startSpaLinkInterception({ exclude: (url) => isExcluded(url, nativePrefixes) });
    createRoot(el).render(<App {...props} />);
  },
  progress: {
    color: '#4B5563',
    delay: 150,
  },
});
