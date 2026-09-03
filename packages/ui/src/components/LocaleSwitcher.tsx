import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@simple-module-py/ui/components/ui/dropdown-menu';
import { useRef } from 'react';
import { cn } from '../lib/utils';

/**
 * Static map of locale code -> label in that locale's own language.
 * Picked before the user can read the current UI language, so labels
 * must not depend on t().
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

// A bordered text pill, not a globe: the code names the language you are in,
// which an icon cannot, and it stays legible on the phone drawer's dark
// surface as well as the topbar's card.
const PILL =
  'inline-flex items-center justify-center rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground';

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  messages: Record<string, string>;
}

export function LocaleSwitcher({ className = '' }: { className?: string }) {
  const page = usePage<{ i18n?: I18nSharedProps }>();
  const i18n = page.props.i18n;
  const formRef = useRef<HTMLFormElement>(null);
  const { t } = useT();

  if (!i18n) return null;
  const code = i18n.locale.toUpperCase();

  // One locale is the default install. A menu that opens onto a single option
  // is noise, but dropping the control entirely leaves the topbar's right
  // cluster looking unfinished — so the pill stays, inert and explained.
  if (i18n.supportedLocales.length <= 1) {
    return (
      <span
        className={cn(PILL, className)}
        title={t(keys.ui.switcher.single_locale, { locale: code })}
      >
        {code}
      </span>
    );
  }

  const select = (locale: string) => {
    if (locale === i18n.locale) return;
    const form = formRef.current;
    if (!form) return;
    const input = form.elements.namedItem('locale') as HTMLInputElement | null;
    if (!input) return;
    input.value = locale;
    form.submit();
  };

  // Just the control — no wrapper. It used to carry the sidebar header's
  // padding and bottom rule, which travelled with it to the topbar and the
  // public nav and painted a stray border in both. Placement belongs to
  // whoever is doing the placing.
  return (
    <>
      <form ref={formRef} method="POST" action="/i18n/set-locale" style={{ display: 'none' }}>
        <input type="hidden" name="locale" value="" readOnly />
      </form>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={t(keys.ui.switcher.label)}
            className={cn(
              PILL,
              'transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
              className,
            )}
          >
            {code}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {i18n.supportedLocales.map((locale) => (
            <DropdownMenuItem
              key={locale}
              onSelect={() => select(locale)}
              data-active={locale === i18n.locale}
            >
              {LOCALE_LABELS[locale] ?? locale}
              {locale === i18n.locale && <span className="ml-auto text-xs">✓</span>}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}
