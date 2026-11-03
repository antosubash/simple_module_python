/**
 * Initial wiring for @simple-module-py/i18n inside the Inertia app.
 *
 * Reads {locale, messages} from Inertia shared props and calls
 * configureI18n on boot; on every successful navigation, adopts whatever
 * catalog the server chose to send (see `subscribeI18nToNavigation`).
 */

import { router } from '@inertiajs/react';
import { activeLocale, configureI18n, updateI18n } from '@simple-module-py/i18n';
import type { SharedProps } from '@simple-module-py/ui/types';

let cachedCatalog: string | undefined;

/** `<locale>:<audience>` of a catalog the server actually sent, else undefined. */
function catalogKey(i18n: SharedProps['i18n'] | undefined): string | undefined {
  return i18n?.messages != null && i18n.audience ? `${i18n.locale}:${i18n.audience}` : undefined;
}

export function bootI18nFromInitialPage(props: Partial<SharedProps>): void {
  const i18n = props.i18n;
  cachedCatalog = catalogKey(i18n);
  if (!i18n) {
    configureI18n({ locale: 'en', messages: {} });
    return;
  }
  configureI18n({ locale: i18n.locale, messages: i18n.messages ?? {} });
}

export function subscribeI18nToNavigation(): () => void {
  let reloading = false;
  const stopBefore = router.on('before', (event) => {
    if (cachedCatalog !== undefined || reloading) {
      event.detail.visit.headers['X-SM-I18n'] = cachedCatalog ?? '';
    }
  });
  const stopSuccess = router.on('success', (event) => {
    const i18n = event.detail.page.props.i18n;
    if (!i18n) return;
    if (i18n.messages != null) {
      updateI18n({ locale: i18n.locale, messages: i18n.messages });
      cachedCatalog = catalogKey(i18n);
      reloading = false;
    } else if (i18n.locale !== activeLocale() && !reloading) {
      reloading = true;
      router.reload({ only: ['i18n'] });
    }
  });
  return () => {
    stopBefore();
    stopSuccess();
  };
}
