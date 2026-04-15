/**
 * Initial wiring for @simple-module/i18n inside the Inertia app.
 *
 * Reads {locale, messages} from Inertia shared props and calls
 * configureI18n on boot; on every successful navigation, checks whether
 * the active locale changed and updates the i18next resources.
 */

import type { PageProps } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { configureI18n, updateI18n } from '@simple-module/i18n';

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  messages: Record<string, string>;
}

export function bootI18nFromInitialPage(props: PageProps): void {
  const i18n = (props as unknown as { i18n?: I18nSharedProps }).i18n;
  if (!i18n) {
    configureI18n({ locale: 'en', messages: {} });
    return;
  }
  configureI18n({ locale: i18n.locale, messages: i18n.messages });
}

let activeLocale: string | null = null;

export function subscribeI18nToNavigation(): () => void {
  return router.on('success', (event) => {
    const i18n = (event.detail.page.props as unknown as { i18n?: I18nSharedProps }).i18n;
    if (!i18n) return;
    if (i18n.locale !== activeLocale) {
      updateI18n({ locale: i18n.locale, messages: i18n.messages });
      activeLocale = i18n.locale;
    }
  });
}
