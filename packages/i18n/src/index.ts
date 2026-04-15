/**
 * Localization primitives — thin wrapper over i18next + react-i18next.
 *
 * Exports the surface the rest of the host consumes:
 *  - configureI18n: call once at boot with the active-locale messages
 *  - updateI18n: call when an Inertia visit brings a new locale
 *  - useT: React hook for translation
 *  - t: non-hook accessor (for use in schemas or utilities)
 */

import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';
// Side-effect import: activates `i18next` module augmentation so every
// consumer of this package gets typed `t()` automatically.
import './types';

type Messages = Record<string, string>;

interface ConfigureOptions {
  locale: string;
  messages: Messages;
}

let configured = false;

export function configureI18n(opts: ConfigureOptions): void {
  if (configured) {
    updateI18n(opts);
    return;
  }
  i18next.use(initReactI18next).init({
    lng: opts.locale,
    fallbackLng: opts.locale,
    resources: {
      [opts.locale]: { translation: opts.messages },
    },
    // Our keys are flat strings-with-dots (e.g. "products.browse.title"),
    // not nested objects. Disable separator processing so i18next looks
    // up the entire key verbatim rather than trying to traverse by dots.
    keySeparator: false,
    nsSeparator: false,
    interpolation: {
      escapeValue: false, // React already escapes
      prefix: '{',
      suffix: '}',
    },
    returnNull: false,
  });
  configured = true;
}

export function updateI18n(opts: ConfigureOptions): void {
  i18next.addResourceBundle(
    opts.locale,
    'translation',
    opts.messages,
    /* deep */ true,
    /* overwrite */ true,
  );
  if (i18next.language !== opts.locale) {
    i18next.changeLanguage(opts.locale);
  }
}

export { t } from 'i18next';
export { useTranslation as useT } from 'react-i18next';
