/**
 * Keeps this tab's catalog in step with the server across Inertia visits.
 *
 * Every visit reports the catalog the tab holds in `X-SM-I18n`
 * (`<locale>:<audience>`), so the server sends `messages` only when this tab
 * needs them, per tab rather than per browser session (#788). A visit that
 * changes locale but arrives without a catalog reloads `i18n` once.
 *
 * Shipped here rather than in each host's `client_app` so a scaffolded app
 * gets it from the package (#871). The router is passed in, which keeps
 * `@inertiajs/react` out of this package's dependencies.
 */

import { activeLocale, configureI18n, updateI18n } from './index';

/** The `i18n` shared prop the backend sends (`build_i18n_block`). */
export interface I18nPageBlock {
  locale: string;
  audience?: string;
  messages: Record<string, string> | null;
}

/** The slice of Inertia's `router` this module uses. */
export interface I18nRouter {
  on(
    event: 'before',
    callback: (event: { detail: { visit: { headers: Record<string, string> } } }) => void,
  ): () => void;
  on(
    event: 'success',
    callback: (event: { detail: { page: { props: Record<string, unknown> } } }) => void,
  ): () => void;
  reload(options: { only: string[]; onFinish: () => void }): void;
}

let cachedCatalog: string | undefined;

/** `<locale>:<audience>` of a catalog the server actually sent, else undefined. */
function catalogKey(i18n: I18nPageBlock | undefined): string | undefined {
  return i18n?.messages != null && i18n.audience ? `${i18n.locale}:${i18n.audience}` : undefined;
}

export function bootI18nFromInitialPage(i18n: I18nPageBlock | undefined): void {
  cachedCatalog = catalogKey(i18n);
  configureI18n({ locale: i18n?.locale ?? 'en', messages: i18n?.messages ?? {} });
}

export function subscribeI18nToNavigation(router: I18nRouter): () => void {
  let reloading = false;
  const stopBefore = router.on('before', (event) => {
    if (cachedCatalog !== undefined || reloading) {
      event.detail.visit.headers['X-SM-I18n'] = cachedCatalog ?? '';
    }
  });
  const stopSuccess = router.on('success', (event) => {
    const i18n = event.detail.page.props.i18n as I18nPageBlock | undefined;
    if (!i18n) return;
    if (i18n.messages != null) {
      updateI18n({ locale: i18n.locale, messages: i18n.messages });
      cachedCatalog = catalogKey(i18n);
      reloading = false;
    } else if (i18n.locale !== activeLocale() && !reloading) {
      reloading = true;
      router.reload({
        only: ['i18n'],
        onFinish: () => {
          reloading = false;
        },
      });
    }
  });
  return () => {
    stopBefore();
    stopSuccess();
  };
}
