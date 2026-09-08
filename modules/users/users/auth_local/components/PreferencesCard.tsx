import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import {
  readThemePreference,
  setThemePreference,
  type ThemePreference,
} from '@simple-module-py/ui/lib/theme';
import { useEffect, useRef, useState } from 'react';

/**
 * Locale label in that locale's own language.
 *
 * Deliberately not translated: the point of the list is to be readable by
 * someone who cannot yet read the current UI language.
 */
const LOCALE_LABELS: Record<string, string> = {
  en: 'English',
  es: 'Español',
  de: 'Deutsch',
  fr: 'Français',
  pt: 'Português',
  ja: '日本語',
  zh: '中文',
  ru: 'Русский',
};

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
}

/**
 * Language and theme.
 *
 * Neither is stored against the account. Language is the existing
 * cookie-backed locale form — the same one the topbar pill posts — and theme
 * is a browser preference, because "dark on my laptop, light on the shared
 * screen" is a property of the screen rather than of the person. The deck's
 * "Task failure emails" toggle is omitted: no notification subsystem exists,
 * and a switch that does nothing is worse than no switch.
 */
export function PreferencesCard() {
  const { t } = useT();
  const i18n = usePage<{ i18n?: I18nSharedProps }>().props.i18n;
  const formRef = useRef<HTMLFormElement>(null);
  // Read in an effect, not during render: `localStorage` is unavailable while
  // the page is server-rendered, and seeding state from it would make the
  // first client render disagree with the markup it is hydrating.
  const [theme, setTheme] = useState<ThemePreference>('system');
  useEffect(() => setTheme(readThemePreference()), []);

  const selectLocale = (locale: string) => {
    if (!i18n || locale === i18n.locale) return;
    const form = formRef.current;
    const input = form?.elements.namedItem('locale') as HTMLInputElement | null;
    if (!form || !input) return;
    input.value = locale;
    form.submit();
  };

  const themeLabels: Record<ThemePreference, string> = {
    light: t(keys.users.profile.theme_light),
    dark: t(keys.users.profile.theme_dark),
    system: t(keys.users.profile.theme_system),
  };

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.profile.preferences_title)}</SectionTitle>
        <div className="space-y-3">
          {i18n && (
            <div className="flex items-center justify-between gap-4 text-sm">
              <span>{t(keys.users.profile.language)}</span>
              <form
                ref={formRef}
                method="POST"
                action="/i18n/set-locale"
                style={{ display: 'none' }}
              >
                <input type="hidden" name="locale" value="" readOnly />
              </form>
              <Select value={i18n.locale} onValueChange={selectLocale}>
                <SelectTrigger
                  className="w-40 max-lg:min-h-11"
                  aria-label={t(keys.users.profile.language)}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {i18n.supportedLocales.map((locale) => (
                    <SelectItem key={locale} value={locale}>
                      {LOCALE_LABELS[locale] ?? locale}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="flex items-center justify-between gap-4 text-sm">
            <span>{t(keys.users.profile.theme)}</span>
            <Select
              value={theme}
              onValueChange={(next) => {
                setTheme(next as ThemePreference);
                setThemePreference(next as ThemePreference);
              }}
            >
              <SelectTrigger
                className="w-40 max-lg:min-h-11"
                aria-label={t(keys.users.profile.theme)}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(['light', 'dark', 'system'] as ThemePreference[]).map((value) => (
                  <SelectItem key={value} value={value}>
                    {themeLabels[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
