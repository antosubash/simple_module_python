/**
 * Initial wiring for @simple-module-py/i18n inside the Inertia app.
 *
 * Reads {locale, messages} from Inertia shared props and calls
 * configureI18n on boot; on every successful navigation, checks whether
 * the active locale changed and updates the i18next resources.
 */

import type { PageProps } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { configureI18n, updateI18n } from '@simple-module-py/i18n';

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  // ``null`` on Inertia XHR visits where the backend skipped the messages
  // payload because the client already has them from the initial page load.
  messages: Record<string, string> | null;
}

export function bootI18nFromInitialPage(props: PageProps): void {
  const i18n = (props as unknown as { i18n?: I18nSharedProps }).i18n;
  if (!i18n) {
    configureI18n({ locale: 'en', messages: {} });
    return;
  }
  configureI18n({ locale: i18n.locale, messages: i18n.messages ?? {} });
  activeLocale = i18n.locale;
}

let activeLocale: string | null = null;

export function subscribeI18nToNavigation(): () => void {
  return router.on('success', (event) => {
    const i18n = (event.detail.page.props as unknown as { i18n?: I18nSharedProps }).i18n;
    if (!i18n) return;
    // A non-null `messages` payload IS the server's signal that the client
    // needs it — it sends `null` whenever the cached catalog is still good.
    // Gating on a locale change instead drops the catalog that arrives when
    // the *audience* changes: logging in swaps the public snapshot for one
    // including admin-only modules, at the same locale, so every admin screen
    // rendered raw keys ("dashboard.home.title") until a hard refresh.
    if (i18n.messages) {
      updateI18n({ locale: i18n.locale, messages: i18n.messages });
      activeLocale = i18n.locale;
    }
  });
}
