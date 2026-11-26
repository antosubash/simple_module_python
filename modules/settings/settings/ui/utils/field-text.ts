import { type TranslationKey, useT } from '@simple-module-py/i18n';
import { useMemo } from 'react';

/** Words a humanised identifier spells in capitals. */
const ACRONYMS = new Set([
  'api',
  'cors',
  'db',
  'dml',
  'http',
  'https',
  'id',
  'ip',
  'jwks',
  'jwt',
  'kb',
  'mime',
  'ms',
  'oidc',
  's3',
  'smtp',
  'sso',
  'tls',
  'ttl',
  'uid',
  'upn',
  'url',
]);

/**
 * The locale key segment for a group heading. Mirrored by `group_slug` in
 * `test_settings_field_translations.py`, which checks the bundled modules.
 */
export function groupSlug(group: string): string {
  return group
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/** `smtp_tls_mode` → "SMTP TLS mode": the last resort, never a raw identifier. */
export function humanize(name: string): string {
  const words = name.split(/[_\s-]+/).filter(Boolean);
  return words
    .map((word, i) => {
      const lower = word.toLowerCase();
      if (ACRONYMS.has(lower)) return lower.toUpperCase();
      return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(' ');
}

type FieldLike = { name: string; title?: string | null; description?: string };
type Lookup = (key: string) => string | undefined;

export type SettingsText = {
  title: () => string;
  description: () => string | undefined;
  label: (field: FieldLike) => string;
  help: (field: FieldLike) => string | undefined;
  group: (group: string) => string;
  /** A select option's label: `fields.<name>.choices.<value>`, else the value. */
  choice: (field: FieldLike, value: string) => string;
};

/**
 * Packages whose settings text ships in another catalog. Host settings are the
 * framework's own fields, so their labels come with `simple_module_hosting`
 * (namespace `hosting`) and reach every app; an app may still override them
 * under its own `host.settings_form.*` keys.
 */
const FALLBACK_NAMESPACE: Record<string, string> = { host: 'hosting' };

/**
 * Text for one module's settings, from `<package>.settings_form.*` locale keys,
 * falling back to what the server declared and then to a humanised identifier.
 */
export function settingsText(pkg: string, lookup: Lookup): SettingsText {
  const fallback = FALLBACK_NAMESPACE[pkg];
  const get = (suffix: string) =>
    lookup(`${pkg}.settings_form.${suffix}`) ||
    (fallback ? lookup(`${fallback}.settings_form.${suffix}`) : undefined) ||
    undefined;
  return {
    title: () => get('title') ?? humanize(pkg),
    description: () => get('description'),
    label: (f) => get(`fields.${f.name}.label`) ?? (f.title || humanize(f.name)),
    help: (f) => get(`fields.${f.name}.help`) ?? (f.description || undefined),
    group: (g) => get(`groups.${groupSlug(g)}`) ?? g,
    // Only plain tokens are key segments; a dotted value would split the key.
    choice: (f, value) =>
      (/^[A-Za-z0-9_-]+$/.test(value) ? get(`fields.${f.name}.choices.${value}`) : undefined) ??
      value,
  };
}

/** A lookup over the active catalogs that answers `undefined` for a missing key. */
export function useLookup(): Lookup {
  const { t, i18n } = useT();
  return useMemo<Lookup>(
    () => (key) => (i18n.exists(key) ? String(t(key as TranslationKey)) : undefined),
    [t, i18n],
  );
}

export function useSettingsText(pkg: string): SettingsText {
  const lookup = useLookup();
  return useMemo(() => settingsText(pkg, lookup), [pkg, lookup]);
}
